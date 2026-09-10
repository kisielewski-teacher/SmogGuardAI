
# -*- coding: utf-8 -*-
"""
Prognozowanie dla O3
Wejście: models/o3_rf.pkl, data/merged_hourly.csv
Wyjście: data/forecast_o3.csv (timestamp, o3_pred)
"""
import pandas as pd
import joblib
from utils_features import ensure_datetime, WEATHER_COLS_DEFAULT, make_supervised, recent_window, iterative_forecast, POLLUTANT_MAP, build_lag_features

MERGED_PATH = 'data/merged_hourly.csv'
MODEL_PATH = 'models/o3_rf.pkl'
HORIZON_HOURS = 24

TARGET = POLLUTANT_MAP['O3']['col']
PRED_COL = POLLUTANT_MAP['O3']['pred_col']
OUT_PATH = POLLUTANT_MAP['O3']['file']

print(f"[INFO] Wczytuję model: {MODEL_PATH}")
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
