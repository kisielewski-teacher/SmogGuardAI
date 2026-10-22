
# -*- coding: utf-8 -*-
"""
⚠️ NIEUŻYWANE (2026-09-27) — stacja GIOŚ w Słupsku (ul. Kniaziewicza) nie ma czujnika NO2, a żadne
inne źródło w projekcie (Syngeos, IMGW) też go nie mierzy. Ten skrypt zawsze kończy się błędem
(0 próbek treningowych) i jest wyłączony z make_all_forecasts.py. Zob. TODO.md. Zostaje w repo na
wypadek, gdyby stacja kiedyś dostała czujnik NO2 (albo dodano nową stację z nim jako źródło).

Trenowanie modelu prognozy dla NO2
Wejście: data/merged_hourly.csv (kolumna timestamp, parametry jakości powietrza + pogoda IMGW)
Wyjście: models/no2_rf.pkl
"""
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from utils_features import ensure_datetime, WEATHER_COLS_DEFAULT, make_supervised, POLLUTANT_MAP

MERGED_PATH = 'data/merged_hourly.csv'
TARGET = POLLUTANT_MAP['NO2']['col']
MODEL_PATH = 'models/no2_rf.pkl'

# Hiperparametry / cechy
LAGS = [1, 2, 3, 6, 12, 24]
ROLLS = [3, 6, 12, 24]

print(f"[INFO] Wczytuję dane: {MERGED_PATH}")
df = pd.read_csv(MERGED_PATH)
df = ensure_datetime(df, col='timestamp')

if TARGET not in df.columns:
    raise ValueError(f"Brak kolumny {TARGET} w {MERGED_PATH}")

# Przygotuj cechy
df_feat, FEATURES = make_supervised(df, TARGET, WEATHER_COLS_DEFAULT, LAGS, ROLLS)

# Usuń wiersze z NaN po dodaniu lagów (pierwsze wiersze siłą rzeczy mają braki)
df_feat = df_feat.dropna(subset=FEATURES + [TARGET])

X = df_feat[FEATURES]
y = df_feat[TARGET]

# Podział train/test (ostatnie 15% jako walidacja chronologiczna)
split_idx = int(len(df_feat) * 0.85)
X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

print(f"[INFO] Rozmiar train: {X_train.shape}, val: {X_val.shape}")

# Model
model = RandomForestRegressor(
    n_estimators=300,
    max_depth=None,
    random_state=42,
    n_jobs=-1
)
model.fit(X_train, y_train)

# Walidacja
pred_val = model.predict(X_val)
mae = mean_absolute_error(y_val, pred_val)
print(f"[METRIC] MAE (val) = {mae:.3f} µg/m³")

# Zapis modelu + konfiguracji cech
payload = {
    'model': model,
    'features': FEATURES,
    'target': TARGET,
    'lags': LAGS,
    'rolls': ROLLS,
}
joblib.dump(payload, MODEL_PATH)
print(f"[SAVE] Zapisano model do: {MODEL_PATH}")
