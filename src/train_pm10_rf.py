# -*- coding: utf-8 -*-
"""
train_pm10_rf.py — skrypt CLI do trenowania modelu Random Forest dla prognozy PM10.

Najważniejsze cechy:
- Domyślny CSV: data/merged_hourly.csv.
- Rozszerzone cechy: czasowe (w tym cykliczne), lagi i średnie kroczące celu, one-hot dla niskiej krotności,
  proste interakcje meteo (uwzględnia polskie nazwy kolumn).
- Auto-detekcja kolumny celu (case-insensitive + aliasy + heurystyka zawierająca 'pm10').
- Diagnostyka: wypis kolumn, CWD, czytelne błędy.
- Zapis: models/pm10_pipeline.pkl + raporty (CSV z ważnościami, TXT ze skrótem drzew).
- **Kompatybilność z różnymi wersjami scikit-learn**: obliczanie RMSE działa niezależnie od wsparcia `squared=False`.
- Usunięte ostrzeżenia deprecacji dot. typów kategorycznych; poprawne użycie `.dt` dla serii czasu.

Przykład:
python train_pm10_rf.py \
  --csv-path data/merged_hourly.csv \
  --target pm10 \
  --time-col timestamp \
  --lags 1 3 6 12 24 \
  --rolling 3 6 12 24 \
  --n-estimators 400 \
  --max-depth 18 \
  --trees-to-print 2 \
  --print-tree-depth 4
"""

from __future__ import annotations
import argparse
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from pandas.api.types import CategoricalDtype  # dla isinstance(..., CategoricalDtype)
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.tree import export_text


# -------------------------------
# Konfiguracja i builder cech
# -------------------------------

@dataclass
class FeatureConfig:
    time_col: str
    target_col: str = "pm10"
    lags: Tuple[int, ...] = (1, 3, 6, 12, 24)
    rolling_windows: Tuple[int, ...] = (3, 6, 12, 24)
    min_periods: Optional[int] = None
    encode_low_cardinality_thresh: int = 24
    include_interactions: bool = True
    require_target_in_transform: bool = True


class ExtendedFeatureBuilder(BaseEstimator, TransformerMixin):
    def __init__(self, config: FeatureConfig):
        self.config = config
        self._feature_names: List[str] = []
        self._base_numeric_cols: List[str] = []
        self._low_card_cat_cols: List[str] = []

    def _infer_columns(self, df: pd.DataFrame) -> None:
        drop_cols = {self.config.time_col, self.config.target_col}
        numeric_cols = [c for c in df.columns if c not in drop_cols and pd.api.types.is_numeric_dtype(df[c])]
        self._base_numeric_cols = numeric_cols

        low_card = []
        for c in df.columns:
            if c in drop_cols:
                continue
            # Obiekty lub kategorie o niskiej krotności
            if pd.api.types.is_object_dtype(df[c]) or isinstance(df[c].dtype, CategoricalDtype):
                nunique = df[c].nunique(dropna=True)
                if nunique <= self.config.encode_low_cardinality_thresh:
                    low_card.append(c)
        self._low_card_cat_cols = low_card

    def _add_time_features(self, ts: pd.Series) -> pd.DataFrame:
        """ts: seria datetime (dtype datetime64) z kolumny czasu"""
        dt = pd.to_datetime(ts, errors="coerce")
        out = pd.DataFrame(index=dt.index)
        out["hour"] = dt.dt.hour
        out["dow"] = dt.dt.dayofweek
        out["month"] = dt.dt.month
        out["is_weekend"] = (out["dow"] >= 5).astype(int)
        # Cykliczne kodowanie
        out["hour_sin"] = np.sin(2 * np.pi * out["hour"] / 24)
        out["hour_cos"] = np.cos(2 * np.pi * out["hour"] / 24)
        out["dow_sin"] = np.sin(2 * np.pi * out["dow"] / 7)
        out["dow_cos"] = np.cos(2 * np.pi * out["dow"] / 7)
        out["month_sin"] = np.sin(2 * np.pi * out["month"] / 12)
        out["month_cos"] = np.cos(2 * np.pi * out["month"] / 12)
        return out

    def _add_lags_rollings(self, s: pd.Series) -> pd.DataFrame:
        out = pd.DataFrame(index=s.index)
        for L in self.config.lags:
            out[f"{self.config.target_col}_lag{L}"] = s.shift(L)
        min_p = self.config.min_periods if self.config.min_periods is not None else None
        for W in self.config.rolling_windows:
            out[f"{self.config.target_col}_rollmean{W}"] = s.shift(1).rolling(window=W, min_periods=min_p).mean()
            out[f"{self.config.target_col}_rollstd{W}"] = s.shift(1).rolling(window=W, min_periods=min_p).std()
        return out

    def _add_interactions(self, df_num: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=df_num.index)
        cols = [c for c in df_num.columns if pd.api.types.is_numeric_dtype(df_num[c])]
        for a in cols:
            # ang/pl warianty nazw prędkości wiatru i wilgotności
            if "wind_speed" in a or "predkosc_wiatru" in a:
                out[f"{a}_sq"] = df_num[a] ** 2
            if "humidity" in a or "wilgotnosc" in a or "rh" in a:
                out[f"{a}_sq"] = df_num[a] ** 2
        return out

    def fit(self, X: pd.DataFrame, y=None):
        if self.config.time_col not in X.columns:
            raise ValueError(f"Brak kolumny czasu: {self.config.time_col}")
        dt = pd.to_datetime(X[self.config.time_col], errors="coerce")
        if dt.isna().any():
            raise ValueError("Nie wszystkie wartości czasu są parsowalne do datetime.")
        self._infer_columns(X)

        feat_names = [
            "hour", "dow", "month", "is_weekend",
            "hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos",
        ]
        feat_names += self._base_numeric_cols

        if self.config.lags or self.config.rolling_windows:
            if self.config.target_col not in X.columns:
                raise ValueError(
                    f"Brak kolumny celu '{self.config.target_col}' do wyliczenia lagów/rollingów podczas fit.")
            for L in self.config.lags:
                feat_names.append(f"{self.config.target_col}_lag{L}")
            for W in self.config.rolling_windows:
                feat_names.append(f"{self.config.target_col}_rollmean{W}")
                feat_names.append(f"{self.config.target_col}_rollstd{W}")

        if self.config.include_interactions:
            for a in self._base_numeric_cols:
                if ("wind_speed" in a or "predkosc_wiatru" in a or
                    "humidity" in a or "wilgotnosc" in a or "rh" in a):
                    feat_names.append(f"{a}_sq")

        self._feature_names = feat_names
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if self.config.time_col not in X.columns:
            raise ValueError(f"Brak kolumny czasu: {self.config.time_col}")
        if (self.config.lags or self.config.rolling_windows) and self.config.require_target_in_transform and (
            self.config.target_col not in X.columns
        ):
            raise ValueError(
                "Brak kolumny celu w transform(), wymagane do wyliczenia lagów/rollingów. "
                "Ustaw require_target_in_transform=False jeśli wiesz co robisz."
            )
        df = X.copy()
        ts = pd.to_datetime(df[self.config.time_col], errors="coerce")
        if ts.isna().any():
            raise ValueError("Nie wszystkie wartości czasu są parsowalne do datetime.")

        # Cechy czasowe
        feats = self._add_time_features(ts)
        # Numeryczne surowe
        if self._base_numeric_cols:
            feats = feats.join(df[self._base_numeric_cols])
        # One-hot nisko-kardynalnych
        if self._low_card_cat_cols:
            dummies = pd.get_dummies(df[self._low_card_cat_cols], dummy_na=False, drop_first=True)
            feats = feats.join(dummies)
        # Lagi/rolling celu
        if (self.config.lags or self.config.rolling_windows) and (self.config.target_col in df.columns):
            lr = self._add_lags_rollings(df[self.config.target_col].astype(float))
            feats = feats.join(lr)
        # Interakcje
        if self.config.include_interactions:
            inter = self._add_interactions(feats)
            feats = feats.join(inter)

        self._feature_names = list(feats.columns)
        return feats

    def get_feature_names_out(self) -> List[str]:
        return list(self._feature_names)


# -------------------------------
# Utilsy
# -------------------------------

def find_time_col(df: pd.DataFrame, preferred: Optional[str] = None) -> str:
    candidates = [preferred] if preferred else []
    candidates += ["timestamp", "datetime", "date", "time"]
    for c in candidates:
        if c and c in df.columns:
            try:
                pd.to_datetime(df[c])
                return c
            except Exception:
                continue
    raise ValueError("Nie znaleziono kolumny czasu. Użyj --time-col, np. --time-col timestamp")


def resolve_target_column(df: pd.DataFrame, requested: str) -> Optional[str]:
    cols = list(df.columns)
    # Dokładnie (case-insensitive)
    for c in cols:
        if c.lower() == requested.lower():
            return c
    # Popularne aliasy
    aliases = [
        requested,
        "pm10", "PM10", "pm_10",
        "pm10_mean", "pm10_avg", "pm10_value", "pm10_concentration",
        "pm_10_mean", "pm10_hourly",
    ]
    low_cols = {c.lower(): c for c in cols}
    for a in aliases:
        if a.lower() in low_cols:
            return low_cols[a.lower()]
    # Heurystyka: cokolwiek zawiera 'pm10'
    for c in cols:
        if 'pm10' in c.lower():
            return c
    return None


def chronological_split(df: pd.DataFrame, time_col: str, test_size: float = 0.2):
    if not 0 < test_size < 1:
        raise ValueError("test_size musi być w (0,1)")
    df_sorted = df.sort_values(time_col)
    n = len(df_sorted)
    split = int(n * (1 - test_size))
    return df_sorted.iloc[:split], df_sorted.iloc[split:]


# -------------------------------
# Trenowanie
# -------------------------------

def train(
    csv_path: str,
    target: str = "pm10",
    time_col: Optional[str] = None,
    lags: Tuple[int, ...] = (1, 3, 6, 12, 24),
    rolling: Tuple[int, ...] = (3, 6, 12, 24),
    test_size: float = 0.2,
    n_estimators: int = 500,
    max_depth: Optional[int] = None,
    n_jobs: int = -1,
    random_state: int = 42,
    include_interactions: bool = True,
    trees_to_print: int = 2,
    print_tree_depth: int = 3,
    model_out: str = "models/pm10_pipeline.pkl",
    save_reports: bool = True,
    sep: str = ",",
    encoding: str = "utf-8",
) -> None:
    # Diagnostyka ścieżki
    if not os.path.isabs(csv_path):
        print(f"[INFO] Bieżący katalog roboczy (CWD): {os.getcwd()}")
        print(f"[INFO] Użyta ścieżka do CSV: {csv_path}")
    csv_abs = os.path.abspath(csv_path)
    if not os.path.exists(csv_abs):
        raise FileNotFoundError(
            f"Nie znaleziono pliku CSV pod ścieżką: {csv_abs}\n"
            f"Podaj pełną ścieżkę (--csv-path) lub uruchom skrypt z katalogu, gdzie leży plik."
        )

    # Wczytanie danych
    df = pd.read_csv(csv_abs, sep=sep, encoding=encoding)

    # Podstawowa diagnostyka
    print("\n[INFO] Kolumny w CSV:")
    print(df.columns.tolist())

    if time_col is None:
        time_col = find_time_col(df)
        print(f"[INFO] Wykryta kolumna czasu: {time_col}")

    # Rozstrzygnięcie kolumny celu
    resolved_target = resolve_target_column(df, target)
    if resolved_target is None:
        raise ValueError(
            f"Brak kolumny celu odpowiadającej '{target}' w {csv_abs}.\n"
            f"Dostępne kolumny: {df.columns.tolist()}\n"
            f"Podaj właściwą nazwę przez --target (np. --target PM10)."
        )
    if resolved_target != target:
        print(f"[INFO] Użyję kolumny celu: '{resolved_target}' (dopasowanie do '{target}')")
    target = resolved_target

    # Jeśli wykryta kolumna celu ma zbyt mało danych, użyj lepszego aliasu.
    # Warunek: całkowicie pusta LUB ma mniej niż 10 wartości (np. tylko syngeos).
    MIN_TARGET_ROWS = 10
    if df[target].notna().sum() < MIN_TARGET_ROWS:
        alt_candidates = [c for c in df.columns if 'pm10' in c.lower() and c != target]
        # posortuj kandydatów malejąco wg liczby nie-NaN wartości
        alt_candidates.sort(key=lambda c: df[c].notna().sum(), reverse=True)
        chosen = None
        for c in alt_candidates:
            if df[c].notna().sum() >= MIN_TARGET_ROWS:
                df[target] = pd.to_numeric(df[c], errors="coerce")
                chosen = c
                print(f"[WARN] Kolumna celu '{target}' ma za mało danych ({df[target].notna().sum()} wierszy) — używam: {c} ({df[target].notna().sum()} wierszy).")
                break
        # dodatkowy fallback: użyj agregatu pm10_mean jeśli występuje
        if chosen is None and 'pm10_mean' in df.columns and df['pm10_mean'].notna().sum() >= MIN_TARGET_ROWS:
            df[target] = pd.to_numeric(df['pm10_mean'], errors="coerce")
            chosen = 'pm10_mean'
            print(f"[WARN] Kolumna celu '{target}' ma za mało danych — używam 'pm10_mean' jako fallback.")
        if chosen is None:
            print(f"[WARN] Kolumna celu '{target}' zawiera tylko NaN lub za mało danych. Spróbuj podać właściwy plik CSV lub upewnij się, że wiersze z PM10 istnieją.")

    # Usunięcie kolumn które SĄ celem lub jego bezpośrednim proxy (data leakage)
    # np. po merge: PM10_x, PM10_y, aqi, pm10_mean, pm25_mean — model nauczyłby się
    # "PM10 = PM10_x" i przewidywał płaską linię w przyszłości.
    leaky_prefixes = ("pm10", "pm25", "aqi", "no2", "o3")
    leaky_cols = [
        c for c in df.columns
        if c.lower() != target.lower()
        and c != time_col
        and any(c.lower().replace("_", "").replace(".", "").startswith(p)
                for p in leaky_prefixes)
    ]
    if leaky_cols:
        print(f"[INFO] Usuwam kolumny proxy celu (leakage): {leaky_cols}")
        df = df.drop(columns=leaky_cols)

    # Usunięcie braków celu
    df = df.dropna(subset=[target])

    # Filtrowanie outlierów: PM10 > 500 µg/m³ jest fizycznie niemożliwe;
    # wyższe wartości to artefakty merge (np. ciśnienie atmosferyczne w kolumnie PM10)
    PM10_MAX_PHYSICAL = 500.0
    outliers = (df[target] > PM10_MAX_PHYSICAL).sum()
    if outliers > 0:
        print(f"[WARN] Odrzucam {outliers} wierszy z {target} > {PM10_MAX_PHYSICAL} (artefakty merge).")
        df = df[df[target] <= PM10_MAX_PHYSICAL]

    # Podział czasowy
    train_df, valid_df = chronological_split(df, time_col=time_col, test_size=test_size)

    # Pipeline
    config = FeatureConfig(
        time_col=time_col,
        target_col=target,
        lags=tuple(lags),
        rolling_windows=tuple(rolling),
        include_interactions=include_interactions,
        require_target_in_transform=True,
    )

    feat_builder = ExtendedFeatureBuilder(config)
    rf = RandomForestRegressor(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=random_state,
        n_jobs=n_jobs,
        oob_score=False,
    )

    pipe = Pipeline([
        ("features", feat_builder),
        ("model", rf),
    ])

    # Fit
    y_train = train_df[target].astype(float)
    pipe.fit(train_df, y_train)

    # Walidacja
    y_valid = valid_df[target].astype(float)
    y_pred = pipe.predict(valid_df)

    mae = mean_absolute_error(y_valid, y_pred)
    # RMSE: kompatybilne z różnymi wersjami sklearn
    try:
        rmse = mean_squared_error(y_valid, y_pred, squared=False)  # nowsze wersje
    except TypeError:
        rmse = np.sqrt(mean_squared_error(y_valid, y_pred))        # starsze wersje
    r2 = r2_score(y_valid, y_pred)

    print("\n===== Metryki walidacyjne =====")
    print(f"MAE : {mae:,.4f}")
    print(f"RMSE: {rmse:,.4f}")
    print(f"R^2 : {r2:,.4f}")

    # Ważności cech
    feature_names = pipe.named_steps["features"].get_feature_names_out()
    importances = pipe.named_steps["model"].feature_importances_
    imp_df = pd.DataFrame({"feature": feature_names, "importance": importances}).sort_values(
        "importance", ascending=False
    )

    print("\n===== Najważniejsze cechy (top 30) =====")
    print(imp_df.head(30).to_string(index=False))

    # Struktura drzew (skrót)
    print("\n===== Struktura wybranych drzew (skrót) =====")
    trees_to_show = min(trees_to_print, len(pipe.named_steps["model"].estimators_))
    for i in range(trees_to_show):
        est = pipe.named_steps["model"].estimators_[i]
        try:
            txt = export_text(est, feature_names=list(feature_names), max_depth=print_tree_depth)
        except Exception:
            txt = export_text(est, max_depth=print_tree_depth)
        print(f"\n--- Drzewo #{i} (max_depth={print_tree_depth}) ---\n{txt}")

    # Zapis pipeline i raportów
    os.makedirs(os.path.dirname(model_out), exist_ok=True)
    joblib.dump(pipe, model_out)
    try:
        print(f"\n✅ Zapisano pipeline do: {model_out}")
    except UnicodeEncodeError:
        print(f"\n[OK] Zapisano pipeline do: {model_out}")

    if save_reports:
        imp_path = os.path.join(os.path.dirname(model_out), "pm10_feature_importances.csv")
        imp_df.to_csv(imp_path, index=False)
        trees_txt_path = os.path.join(os.path.dirname(model_out), "pm10_trees.txt")
        with open(trees_txt_path, "w", encoding="utf-8") as f:
            for i in range(trees_to_show):
                est = pipe.named_steps["model"].estimators_[i]
                try:
                    txt = export_text(est, feature_names=list(feature_names), max_depth=print_tree_depth)
                except Exception:
                    txt = export_text(est, max_depth=print_tree_depth)
                f.write(f"\n--- Drzewo #{i} (max_depth={print_tree_depth}) ---\n{txt}\n")
        try:
            print(f"📄 Zapisano ważności: {imp_path}")
        except UnicodeEncodeError:
            print(f"[OK] Zapisano ważności: {imp_path}")
        try:
            print(f"🌳 Zapisano strukturę drzew: {trees_txt_path}")
        except UnicodeEncodeError:
            print(f"[OK] Zapisano strukturę drzew: {trees_txt_path}")


# -------------------------------
# CLI
# -------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Trenowanie Random Forest dla PM10 (pipeline + rozszerzone cechy)")
    p.add_argument("--csv-path", type=str, default="data/merged_hourly.csv", help="Ścieżka do pliku CSV z danymi (domyślnie data/merged_hourly.csv)")
    p.add_argument("--target", type=str, default="pm10", help="Nazwa kolumny celu (case-insensitive; obsługa aliasów PM10)")
    p.add_argument("--time-col", type=str, default=None, help="Nazwa kolumny czasu (jeśli nie podasz, spróbujemy wykryć)")
    p.add_argument("--lags", type=int, nargs="*", default=[1, 3, 6, 12, 24], help="Lagi celu (godziny)")
    p.add_argument("--rolling", type=int, nargs="*", default=[3, 6, 12, 24], help="Okna średnich kroczących (godziny)")
    p.add_argument("--test-size", type=float, default=0.2, help="Udział zbioru walidacyjnego (chronologicznie)")
    p.add_argument("--n-estimators", type=int, default=500, help="Liczba drzew w lesie")
    p.add_argument("--max-depth", type=int, default=None, help="Maksymalna głębokość drzew (None=bez limitu)")
    p.add_argument("--n-jobs", type=int, default=-1, help="Równoległość w RandomForest (-1 = wszystkie rdzenie)")
    p.add_argument("--random-state", type=int, default=42, help="Ziarno losowe")
    p.add_argument("--no-interactions", action="store_true", help="Wyłącz proste interakcje meteo")
    p.add_argument("--trees-to-print", type=int, default=2, help="Ile drzew wydrukować")
    p.add_argument("--print-tree-depth", type=int, default=3, help="Maksymalna głębokość wydruku drzewa")
    p.add_argument("--model-out", type=str, default="models/pm10_pipeline.pkl", help="Ścieżka zapisu pipeline")
    p.add_argument("--no-save-reports", action="store_true", help="Nie zapisuj CSV i TXT z raportami")
    p.add_argument("--sep", type=str, default=",", help="Separator CSV (domyślnie ,)")
    p.add_argument("--encoding", type=str, default="utf-8", help="Kodowanie CSV (domyślnie utf-8)")
    return p.parse_args()


def main():
    args = parse_args()
    train(
        csv_path=args.csv_path,
        target=args.target,
        time_col=args.time_col,
        lags=tuple(args.lags),
        rolling=tuple(args.rolling),
        test_size=args.test_size,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        n_jobs=args.n_jobs,
        random_state=args.random_state,
        include_interactions=not args.no_interactions,
        trees_to_print=args.trees_to_print,
        print_tree_depth=args.print_tree_depth,
        model_out=args.model_out,
        save_reports=not args.no_save_reports,
        sep=args.sep,
        encoding=args.encoding,
    )


if __name__ == "__main__":
    main()
