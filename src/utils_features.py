
# -*- coding: utf-8 -*-
"""
Narzędzia do przygotowania cech i prognozowania wielogodzinnego.
Wymagania: pandas, numpy, scikit-learn
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple

WEATHER_COLS_DEFAULT = [
    "temperatura", "predkosc_wiatru", "wilgotnosc_wzgledna",
    "suma_opadu", "cisnienie"
]

POLLUTANT_MAP = {
    "PM10": {"col": "PM10", "pred_col": "pm10_pred", "file": "data/forecast_pm10.csv"},
    "PM2.5": {"col": "PM2.5", "pred_col": "pm25_pred", "file": "data/forecast_pm25.csv"},
    "NO2": {"col": "NO2", "pred_col": "no2_pred", "file": "data/forecast_no2.csv"},
    "O3": {"col": "O3", "pred_col": "o3_pred", "file": "data/forecast_o3.csv"},
}

def ensure_datetime(df: pd.DataFrame, col: str = "timestamp") -> pd.DataFrame:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors='coerce')
        df = df.dropna(subset=[col])
        df = df.sort_values(col)
    return df

def build_lag_features(df: pd.DataFrame, target_col: str,
                       lags: List[int], rolls: List[int]) -> pd.DataFrame:
    """Dodaje opóźnienia (lag) i średnie kroczące (rolling) do danych."""
    out = df.copy()
    for L in lags:
        out[f"{target_col}_lag{L}"] = out[target_col].shift(L)
    for W in rolls:
        out[f"{target_col}_roll{W}"] = out[target_col].rolling(W, min_periods=1).mean().shift(1)
    return out

def make_supervised(df: pd.DataFrame, target_col: str,
                    weather_cols: List[str], lags: List[int], rolls: List[int]) -> Tuple[pd.DataFrame, List[str]]:
    """Zwraca ramkę z cechami i listę nazw cech."""
    df = build_lag_features(df, target_col, lags, rolls)
    features = [
        *(f"{target_col}_lag{L}" for L in lags),
        *(f"{target_col}_roll{W}" for W in rolls),
        *(c for c in weather_cols if c in df.columns)
    ]
    return df, features

def recent_window(df: pd.DataFrame, target_col: str, n: int = 48) -> pd.DataFrame:
    """Zwraca ostatnie n wierszy (dla prognozy wielogodzinnej)."""
    return df.tail(n).copy()

def iterative_forecast(model, hist_df: pd.DataFrame, target_col: str, features: List[str],
                       horizon_hours: int, ts_col: str = "timestamp",
                       freq: str = 'H') -> pd.DataFrame:
    """
    Autoregresyjna prognoza krok-po-kroku: przewidujemy kolejne godziny,
    aktualizując opóźnienia na bazie poprzednich predykcji.
    """
    # Kopia danych i ostatni znany znacznik czasu
    df = hist_df.copy()
    last_ts = df[ts_col].max()
    preds = []

    for h in range(1, horizon_hours + 1):
        # Wyznacz kolejny timestamp
        next_ts = last_ts + pd.Timedelta(hours=1)
        # Wylicz cechy dla wiersza next_ts: opóźnienia względem aktualnego df
        row = {}
        for f in features:
            if f.endswith('_lag1'):
                row[f] = df[target_col].iloc[-1]
            elif '_lag' in f:
                # lagX dla następnego kroku (next_ts) = wartość sprzed L godzin
                # względem next_ts, czyli L-1 godzin przed ostatnim znanym punktem df.
                L = int(f.split('_lag')[-1])
                row[f] = df[target_col].iloc[-L] if len(df) >= L else np.nan
            elif '_roll' in f:
                W = int(f.split('_roll')[-1])
                row[f] = df[target_col].rolling(W, min_periods=1).mean().iloc[-1]
            else:
                # cecha pogodowa – przyjmujemy ostatnią dostępną wartość
                row[f] = df[f].iloc[-1] if f in df.columns else np.nan
        # Uzupełnij brakujące wartości prostym forward-fill z ostatnich znanych
        for k in list(row.keys()):
            if pd.isna(row[k]):
                # jeśli brakuje, użyj ostatniej wartości cechy, jeśli istnieje
                if k in df.columns:
                    row[k] = df[k].iloc[-1]
                else:
                    row[k] = 0.0
        X = pd.DataFrame([row])
        yhat = float(model.predict(X)[0])
        preds.append({ts_col: next_ts, 'pred': yhat})
        # Dopisz przewidywaną wartość jako "rzeczywistą" do df, aby cechy lag się aktualizowały
        new_row = {ts_col: next_ts, target_col: yhat}
        # zachowaj też pogodę (ostatnie wartości), aby cechy były kompletne
        for f in features:
            if f in df.columns and f not in new_row:
                new_row[f] = df[f].iloc[-1]
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        last_ts = next_ts

    return pd.DataFrame(preds)
