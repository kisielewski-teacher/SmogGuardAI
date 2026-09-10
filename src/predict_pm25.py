
# -*- coding: utf-8 -*-
"""
Prognozowanie dla PM2.5
Wejście: models/pm25_rf.pkl, data/merged_hourly.csv
Wyjście: data/forecast_pm25.csv (timestamp, pm25_pred)
"""
import pandas as pd
import joblib
import os
import sys
from utils_features import ensure_datetime, WEATHER_COLS_DEFAULT, make_supervised, recent_window, iterative_forecast, POLLUTANT_MAP, build_lag_features

MERGED_PATH = 'data/merged_hourly.csv'
MODEL_PATH = 'models/pm25_rf.pkl'
HORIZON_HOURS = 24

TARGET = POLLUTANT_MAP['PM2.5']['col']
PRED_COL = POLLUTANT_MAP['PM2.5']['pred_col']
OUT_PATH = POLLUTANT_MAP['PM2.5']['file']

print(f"[INFO] Wczytuję model: {MODEL_PATH}")
if not os.path.exists(MODEL_PATH):
    print(f"[WARN] Model {MODEL_PATH} nie istnieje — tworzę fallback prognozę PM2.5 (persistence/syngeos).")
    df = pd.read_csv(MERGED_PATH)
    df = ensure_datetime(df, col='timestamp')
    # znajdź ostatnią dostępną wartość PM2.5 (albo pm25_mean z syngeos)
    last_val = None
    for col in [TARGET, 'pm25_mean', 'pm25', 'PM2.5', 'pm_25']:
        if col in df.columns and df[col].notna().any():
            last_val = float(df[df[col].notna()].sort_values('timestamp')[col].iloc[-1])
            break
    if last_val is None:
        last_val = 0.0
    rows = []
    base = df['timestamp'].max()
    base = pd.to_datetime(base)
    for h in range(1, HORIZON_HOURS + 1):
        rows.append({'timestamp': (base + pd.Timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S'), PRED_COL: last_val})
    pd.DataFrame(rows).to_csv(OUT_PATH, index=False)
    print(f"[SAVE] Zapisano fallback prognozę PM2.5 do: {OUT_PATH}")
    sys.exit(0)

payload = joblib.load(MODEL_PATH)
model = payload['model']
FEATURES = payload['features']
LAGS = payload['lags']
ROLLS = payload['rolls']

print(f"[INFO] Wczytuję dane scalone: {MERGED_PATH}")
df = pd.read_csv(MERGED_PATH)
df = ensure_datetime(df, col='timestamp')

# Przygotuj cechy zgodnie z saved config

df_feat = build_lag_features(df, TARGET, LAGS, ROLLS)
window = recent_window(df_feat, TARGET, n=48)

# Iteratywna prognoza
fc = iterative_forecast(model, window, TARGET, FEATURES, HORIZON_HOURS, ts_col='timestamp', freq='H')
fc.rename(columns={'pred': PRED_COL}, inplace=True)

fc.to_csv(OUT_PATH, index=False)
print(f"[SAVE] Zapisano prognozę do: {OUT_PATH}")
