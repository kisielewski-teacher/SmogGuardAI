
# -*- coding: utf-8 -*-
r"""
predict_pm10.py — predykcja PM10 z cech + generowanie przyszłości (--horizon),
z wyrównaniem startu do ostatniego pomiaru (GIOŚ) przez --align-to.

Użycie:
py src\\predict_pm10.py ^
  --features data\\features_pm10.csv ^
  --model models\\pm10_rf.pkl ^
  --out outputs\\pm10_pred_latest.csv ^
  --horizon 24 ^
  --align-to data\\gios_slupsk.csv ^
  --verbose
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import joblib
import sys
try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    from train_pm10_rf import ExtendedFeatureBuilder, FeatureConfig
    sys.modules['__main__'].ExtendedFeatureBuilder = ExtendedFeatureBuilder
    sys.modules['__main__'].FeatureConfig = FeatureConfig
except Exception:
    pass

from utils_features import resolve_best_target_alias


def pred_col_name(target_col: str) -> str:
    """Nazwa kolumny wynikowej zgodna z targetem: 'PM10' -> 'pm10_pred', 'PM2.5' -> 'pm25_pred'.
    Musi być spójna z tym, czego oczekuje merge_pm10_results.py (--pollutant pm10|pm25) —
    inaczej scalanie po cichu dostaje same NaN (kolumna 'pm25_pred' nie istnieje, bo
    predykcja zawsze nazywała się 'pm10_pred', nawet dla PM2.5)."""
    base = target_col.lower().replace(".", "").replace("_", "")
    return f"{base}_pred"


def target_col_of(model) -> str | None:
    """Nazwa kolumny celu zapisana w wytrenowanym pipeline (np. 'PM10' albo 'PM2.5')."""
    fb = getattr(model, "named_steps", {}).get("features") if hasattr(model, "named_steps") else None
    if fb is not None and hasattr(fb, "config"):
        return fb.config.target_col
    return None


ALIASES_TIME = ["timestamp", "time", "date", "datetime", "DateTime"]

# Mapowanie kolumn w merged_hourly → nazwy Open-Meteo
_WX_COL_MAP = {
    "temperatura_x":         "temperature_2m",
    "temperatura_y":         "temperature_2m",
    "wilgotnosc_wzgledna_x": "relative_humidity_2m",
    "wilgotnosc_wzgledna_y": "relative_humidity_2m",
    "cisnienie_x":           "surface_pressure",
    "cisnienie_y":           "surface_pressure",
    "predkosc_wiatru_x":     "wind_speed_10m",
    "predkosc_wiatru_y":     "wind_speed_10m",
    "wg":                    "wind_gusts_10m",
}


def fetch_weather_forecast(horizon: int, lat: float = 54.463, lon: float = 17.047,
                            verbose: bool = False) -> pd.DataFrame:
    """Pobiera prognozę pogody z Open-Meteo na najbliższe `horizon` godzin (bez API key)."""
    if not _HAS_REQUESTS:
        return pd.DataFrame()
    # Open-Meteo zwraca forecast_days pełnych dni kalendarzowych liczonych od
    # północy (nie od "teraz") — przy horyzoncie 72h i popołudniowym uruchomieniu
    # 3 dni by nie starczyły do pokrycia całych 72h od bieżącej godziny, dlatego
    # bierzemy zapas +1 dzień ponad to, co wynika z samego horyzontu.
    forecast_days = min(16, max(3, (horizon // 24) + 2))
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,relative_humidity_2m,surface_pressure,"
        f"wind_speed_10m,wind_gusts_10m"
        f"&forecast_days={forecast_days}&timezone=Europe/Warsaw&wind_speed_unit=ms"
    )
    try:
        r = _requests.get(url, timeout=15)
        r.raise_for_status()
        h = r.json()["hourly"]
        df = pd.DataFrame({
            "timestamp":            pd.to_datetime(h["time"]),
            "temperature_2m":       h["temperature_2m"],
            "relative_humidity_2m": h["relative_humidity_2m"],
            "surface_pressure":     h["surface_pressure"],
            "wind_speed_10m":       h["wind_speed_10m"],
            "wind_gusts_10m":       h["wind_gusts_10m"],
        })
        if verbose:
            print(f"[INFO] Prognoza pogody: {len(df)} godzin, zakres "
                  f"{df['timestamp'].min()} – {df['timestamp'].max()}")
        return df
    except Exception as e:
        if verbose:
            print(f"[WARN] Nie udało się pobrać prognozy pogody: {e}")
        return pd.DataFrame()


def iterative_future_predict(pipe, df_hist: pd.DataFrame, time_col: str,
                              horizon: int, weather_fc: pd.DataFrame,
                              last_ts: pd.Timestamp, verbose: bool = False) -> pd.DataFrame:
    """
    Iteracyjna predykcja wielokrokowa:
    - Krok h+1 używa poprzedniej predykcji jako lag1
    - Kolumny pogodowe aktualizowane z Open-Meteo forecast
    - Zwraca DataFrame z kolumnami: timestamp, pm10_pred
    """
    fb = pipe.named_steps["features"]
    final_est = pipe.named_steps["model"]
    target_col = fb.config.target_col
    out_col = pred_col_name(target_col)
    expected_features = list(getattr(final_est, "feature_names_in_",
                                     fb.get_feature_names_out()))

    # Bufor historii — ostatnie max(lags) wierszy, żeby lagi były dobrze wyliczone
    max_lag = max(fb.config.lags) if fb.config.lags else 24
    max_win = max(fb.config.rolling_windows) if fb.config.rolling_windows else 24
    keep_rows = max(max_lag, max_win) + 5
    working_df = df_hist.tail(keep_rows).copy()

    predictions = []
    future_timestamps = pd.date_range(last_ts + pd.Timedelta(hours=1),
                                       periods=horizon, freq="h")

    for i, next_ts in enumerate(future_timestamps):
        # Buduj nowy wiersz na bazie ostatniego historycznego
        new_row = working_df.iloc[-1].copy()
        new_row[time_col] = next_ts

        # Ustaw PM10 na wygładzoną wartość z ostatnich predykcji (EMA 0.4)
        # — zapobiega oscylacjom AR przy ujemnej autokorelacji lag-1
        if predictions:
            # Exponential moving average ostatnich kroków zamiast surowej ostatniej pred.
            alpha = 0.4
            ema = predictions[-1]
            for p in reversed(predictions[-4:-1]):
                ema = alpha * ema + (1 - alpha) * p
            smoothed = round(ema, 2)
            new_row[target_col] = smoothed
            # Aliasy tego samego zanieczyszczenia (PM10_x/PM10_y/pm10_mean albo
            # PM2.5_x/PM2.5_y/pm25_mean) też trzeba zaktualizować, inaczej kolejny
            # krok policzy lag na bazie nieaktualnej/skrośnej kolumny.
            alias_base = target_col.lower().replace(".", "").replace("_", "")
            for alias in (f"{target_col}_x", f"{target_col}_y", f"{alias_base}_mean"):
                if alias in new_row.index:
                    new_row[alias] = smoothed

        # Aktualizuj kolumny pogodowe z prognozy (jeśli dostępna)
        if not weather_fc.empty:
            # Znajdź najbliższy timestamp w prognozie
            deltas = (weather_fc["timestamp"] - next_ts).abs()
            idx = deltas.idxmin()
            if deltas[idx] <= pd.Timedelta(hours=2):
                wx = weather_fc.loc[idx]
                for col, wx_key in _WX_COL_MAP.items():
                    if col in new_row.index and wx_key in wx.index:
                        new_row[col] = wx[wx_key]

        # Dołącz wiersz i policz cechy dla całego working_df
        working_df = pd.concat(
            [working_df, pd.DataFrame([new_row])], ignore_index=True
        )

        # Uruchom feature builder na całości (lagi liczone na całej serii)
        X_feat = fb.transform(working_df)
        X_row = X_feat.tail(1).reindex(columns=expected_features, fill_value=0.0)

        pred = float(final_est.predict(X_row)[0])
        pred = max(0.0, round(pred, 2))
        predictions.append(pred)

        if verbose and i < 3:
            print(f"  h+{i+1} ({next_ts}): {out_col}={pred:.1f}")

    return pd.DataFrame({"timestamp": future_timestamps, out_col: predictions})

def build_parser():
    ap = argparse.ArgumentParser(description="Predykcja PM10 (24h) z wyrównaniem do WAQI.")
    ap.add_argument("--features", required=True, help="CSV z cechami (data/features_pm10.csv)")
    ap.add_argument("--model", required=True, help="Model (models/pm10_rf.pkl)")
    ap.add_argument("--out", required=True, help="Wyjście CSV (outputs/pm10_pred_latest.csv)")
    ap.add_argument("--time-col", default="timestamp", help="Kolumna czasu (domyślnie: timestamp)")
    ap.add_argument("--predict-all", action="store_true", help="Licz dla wszystkich wierszy cech")
    ap.add_argument("--horizon", type=int, default=24, help="Godziny do przodu (domyślnie 24)")
    ap.add_argument("--align-to", default=None, help="CSV z pomiarami (np. data/gios_slupsk.csv) do wyrównania startu przyszłości")
    ap.add_argument("--verbose", action="store_true", help="Debug wypisywany na konsolę")
    return ap

def normalize_timestamp(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    if time_col not in df.columns:
        for a in ALIASES_TIME:
            if a in df.columns:
                df = df.rename(columns={a: time_col})
                break
    if time_col not in df.columns:
        raise RuntimeError(f"Brak kolumny czasu: {time_col}")
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col]).copy()
    try:
        if str(df[time_col].dtype).startswith("datetime64[ns,"):
            df[time_col] = df[time_col].dt.tz_convert("Europe/Warsaw").dt.tz_localize(None)
    except Exception:
        pass
    return df

EXCLUDE = {"timestamp", "pm10_true", "PM10", "pm10"}

def choose_feature_columns(df: pd.DataFrame, model) -> list[str]:
    if hasattr(model, "feature_names_in_"):
        expected = [c for c in model.feature_names_in_ if c not in EXCLUDE]
        missing = [c for c in expected if c not in df.columns]
        if missing:
            raise RuntimeError("Brakuje kolumn cech oczekiwanych przez model: " + ", ".join(missing))
        return expected
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    return [c for c in num_cols if c not in EXCLUDE]

def read_csv_robust(path: Path) -> pd.DataFrame:
    sep = ","
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            h = f.readline()
            if ";" in h and "," not in h:
                sep = ";"
    except Exception:
        pass
    try:
        return pd.read_csv(path, sep=sep)
    except pd.errors.ParserError:
        return pd.read_csv(path, sep=sep, engine="python", on_bad_lines="skip")

def get_last_meas_ts(align_path: str | None, time_col: str) -> pd.Timestamp | None:
    if not align_path:
        return None
    p = Path(align_path)
    if not p.exists():
        return None
    dfm = read_csv_robust(p)
    dfm = normalize_timestamp(dfm, time_col)
    if dfm.empty:
        return None
    return dfm[time_col].max()

def build_future_frame(df_feats: pd.DataFrame, time_col: str, horizon: int,
                       align_last_meas: pd.Timestamp | None) -> pd.DataFrame:
    if "pm10_true" in df_feats.columns and df_feats["pm10_true"].notna().any():
        last_true_feats = df_feats[df_feats["pm10_true"].notna()][time_col].max()
    else:
        last_true_feats = df_feats[time_col].max()

    start_anchor = last_true_feats
    if align_last_meas is not None and align_last_meas > start_anchor:
        start_anchor = align_last_meas

    future_index = pd.date_range(start_anchor + pd.Timedelta(hours=1), periods=horizon, freq="h")

    base_row = df_feats[df_feats[time_col] <= start_anchor].tail(1)
    if base_row.empty:
        base_row = df_feats.tail(1)
    base = pd.DataFrame([base_row.squeeze()] * horizon)
    base[time_col] = future_index

    base["hour"] = base[time_col].dt.hour
    base["dow"] = base[time_col].dt.day_of_week
    base["is_weekend"] = (base["dow"] >= 5).astype(int)
    base["month"] = base[time_col].dt.month
    return base

def main():
    args = build_parser().parse_args()
    fpath = Path(args.features)
    mpath = Path(args.model)
    opath = Path(args.out)

    if not fpath.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku cech: {fpath}")
    if not mpath.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku modelu: {mpath}")

    df = read_csv_robust(fpath)
    df = normalize_timestamp(df, args.time_col)
    df = df.drop_duplicates(subset=[args.time_col]).sort_values(args.time_col)

    last_meas_ts = get_last_meas_ts(args.align_to, args.time_col)
    model = joblib.load(mpath)

    # Jeżeli plik wejściowy pochodzi z merge_hourly, kolumna celu (PM10, PM2.5, ...)
    # może mieć mniej danych niż jej alias (po złączeniu z IMGW/innymi źródłami
    # pandas dodaje sufiks _x/_y, albo dane leżą w 'pm10_mean'/'pm25_mean').
    # Ustal nazwę celu z wytrenowanego modelu (działa dla dowolnego zanieczyszczenia)
    # i uzupełnij ją z najlepszego dostępnego aliasu — patrz utils_features.py.
    model_target = target_col_of(model)
    if model_target and model_target in df.columns:
        best_alias, best_count = resolve_best_target_alias(df, model_target)
        if best_alias is not None:
            df[model_target] = pd.to_numeric(df[best_alias], errors="coerce")

    out_col = pred_col_name(model_target) if model_target else "pm10_pred"
    true_col = f"{model_target.lower().replace('.', '').replace('_', '')}_true" if model_target else "pm10_true"
    if not args.predict_all and true_col in df.columns:
        df_hist_future = df[df[true_col].isna()].copy()
    else:
        df_hist_future = df.copy()

    # ── Predykcja historyczna (wiersze bez pm10_true) ────────────────────────
    if hasattr(model, "named_steps"):
        pipe = model
        fb = pipe.named_steps.get("features")
        final_est = pipe.named_steps.get("model")
        if fb is not None and final_est is not None:
            X_feat = fb.transform(df_hist_future)
            expected = list(getattr(final_est, "feature_names_in_",
                                    fb.get_feature_names_out()))
            X_aligned = X_feat.reindex(columns=expected, fill_value=0.0)
            if args.verbose:
                print(f"[DEBUG] Pipeline features -> X_aligned.shape={X_aligned.shape}")
            yhat_hist = final_est.predict(X_aligned)
        else:
            yhat_hist = pipe.predict(df_hist_future)
    else:
        feat_cols = choose_feature_columns(df_hist_future, model)
        X = df_hist_future[feat_cols].copy().apply(pd.to_numeric, errors="coerce")
        for c in X.columns:
            if X[c].isna().any():
                m = float(np.nanmean(X[c].values)) if np.isfinite(np.nanmean(X[c].values)) else 0.0
                X[c] = X[c].fillna(m)
        yhat_hist = model.predict(X)

    hist_pred_df = pd.DataFrame({
        "timestamp": df_hist_future[args.time_col].values,
        out_col: yhat_hist.astype(float),
    })

    # ── Iteracyjna predykcja przyszłości z prognozą pogody ───────────────────
    if args.horizon > 0:
        if args.verbose:
            print(f"[INFO] Pobieram prognozę pogody Open-Meteo na {args.horizon}h...")
        weather_fc = fetch_weather_forecast(args.horizon, verbose=args.verbose)

        anchor_ts = last_meas_ts if last_meas_ts is not None else df[args.time_col].max()

        if hasattr(model, "named_steps") and fb is not None:
            future_pred_df = iterative_future_predict(
                pipe=model,
                df_hist=df,
                time_col=args.time_col,
                horizon=args.horizon,
                weather_fc=weather_fc,
                last_ts=anchor_ts,
                verbose=args.verbose,
            )
        else:
            df_future = build_future_frame(df, args.time_col, args.horizon, last_meas_ts)
            feat_cols = choose_feature_columns(df_future, model)
            X_f = df_future[feat_cols].copy().apply(pd.to_numeric, errors="coerce").fillna(0.0)
            future_pred_df = pd.DataFrame({
                "timestamp": df_future[args.time_col].values,
                out_col: model.predict(X_f).astype(float),
            })

        out_df = pd.concat([hist_pred_df, future_pred_df], ignore_index=True).sort_values("timestamp")
    else:
        out_df = hist_pred_df.sort_values("timestamp")

    opath.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(opath, index=False)
    print(f"[OK] Zapisano predykcję: {opath} (wierszy: {len(out_df)})")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Przy błędach (np. brak punktu startowego dla przyszłości) wyświetlmy ostrzeżenie
        # i zwróćmy zero, aby pipeline kontynuował.
        print(f"[WARN] predict_pm10.py zakończony wyjątkiem: {e}")
        sys.exit(0)
