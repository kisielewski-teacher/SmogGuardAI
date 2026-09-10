
# -*- coding: utf-8 -*-
r"""
predict.py — generuje plik z prognozą PM10 na podstawie tabeli cech i zapisanego modelu.

Użycie:
    py src\predict.py --features data\features_pm10.csv --model models\pm10_rf.pkl --out outputs\pm10_pred_latest.csv

Wejście (features):
- Plik CSV z kolumną czasu (np. 'timestamp') oraz kolumnami cech (numerycznymi).
- Jeśli plik zawiera 'pm10_true', to domyślnie prognozy liczymy dla wierszy bez tej kolumny (przyszłość).
  Jeśli użyjesz --predict-all, prognozy będą liczone dla wszystkich wierszy.

Wyjście:
- CSV: 'timestamp','pm10_pred' (naive datetime64[ns], bez strefy czasowej)
"""
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import joblib

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Predykcja PM10 z tabeli cech i modelu.")
    ap.add_argument("--features", required=True, help="Ścieżka do pliku cech (CSV), np. data/features_pm10.csv")
    ap.add_argument("--model", required=True, help="Ścieżka do pliku modelu, np. models/pm10_rf.pkl")
    ap.add_argument("--out", required=True, help="Ścieżka wyjściowa CSV, np. outputs/pm10_pred_latest.csv")
    ap.add_argument("--time-col", default="timestamp", help="Nazwa kolumny czasu (domyślnie: timestamp)")
    ap.add_argument("--predict-all", action="store_true",
                    help="Jeśli podane, licz predykcje dla wszystkich wierszy (nie tylko przyszłość).")
    return ap

def normalize_timestamp(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    # aliasy czasu
    if time_col not in df.columns:
        for alias in ["time", "date", "datetime", "DateTime"]:
            if alias in df.columns:
                df = df.rename(columns={alias: time_col})
                break
    if time_col not in df.columns:
        raise RuntimeError(f"Brak kolumny czasu: {time_col}")

    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col]).copy()

    # jeśli tz-aware → Europe/Warsaw → naive
    try:
        if str(df[time_col].dtype).startswith("datetime64[ns,"):
            df[time_col] = df[time_col].dt.tz_convert("Europe/Warsaw").dt.tz_localize(None)
    except Exception:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    return df

def choose_feature_columns(df: pd.DataFrame, model) -> list[str]:
    """
    Wybierz kolumny cech:
    - jeśli model ma feature_names_in_: weź dokładnie ten zestaw (przecięcie z df.columns)
    - wyklucz typowe nie-cechy: 'timestamp', 'pm10_true', 'PM10', 'pm10'
    """
    exclude = {"timestamp", "pm10_true", "PM10", "pm10"}
    if hasattr(model, "feature_names_in_"):
        expected = [c for c in model.feature_names_in_ if c not in exclude]
        # sprawdź braki
        missing = [c for c in expected if c not in df.columns]
        if missing:
            raise RuntimeError(f"Brakuje kolumn cech oczekiwanych przez model: {missing}. "
                               f"Upewnij się, że generujesz features tym samym pipeline'em co trening.")
        return expected
    # fallback: wszystkie numeryczne poza exclude
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    return [c for c in num_cols if c not in exclude]

def main():
    args = build_parser().parse_args()

    features_path = Path(args.features)
    model_path = Path(args.model)
    out_path = Path(args.out)

    if not features_path.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku cech: {features_path}")
    if not model_path.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku modelu: {model_path}")

    # Wczytaj cechy
    df = pd.read_csv(features_path)
    df = normalize_timestamp(df, args.time_col)

    # Wiersze do predykcji: domyślnie przyszłość (tam, gdzie brak pm10_true)
    if not args.predict_all and "pm10_true" in df.columns:
        pred_mask = df["pm10_true"].isna()
    else:
        pred_mask = pd.Series(True, index=df.index)

    df_pred_input = df.loc[pred_mask].copy()
    if df_pred_input.empty:
        raise RuntimeError("Brak wierszy do predykcji (rozważ --predict-all).")

    # Wybierz kolumny cech pod model (i w odpowiedniej kolejności)
    model = joblib.load(model_path)
    feat_cols = choose_feature_columns(df_pred_input, model)
    X = df_pred_input[feat_cols]

    # Predykcja
    yhat = model.predict(X)
    out_df = pd.DataFrame({
        "timestamp": df_pred_input[args.time_col].values,
        "pm10_pred": yhat.astype(float)
    }).sort_values("timestamp")

    # Zapis
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    print(f"[OK] Zapisano predykcję: {out_path} (wierszy: {len(out_df)})")

if __name__ == "__main__":
    main()
