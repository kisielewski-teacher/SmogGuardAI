
# test_predict_on_history.py
import joblib
import pandas as pd
import numpy as np

MODEL_PATH = "models/pm10_rf.pkl"
DATA_PATH = "data/merged_hourly.csv"
TS_COL = "timestamp"
TARGET = "PM10"

# 1) Wczytaj model
model = joblib.load(MODEL_PATH)
feats = list(getattr(model, "feature_names_in_", []))
print("Cechy w modelu:", feats)

# 2) Wczytaj historię i uporządkuj czas
df = pd.read_csv(DATA_PATH)
df.columns = df.columns.str.strip()
df[TS_COL] = pd.to_datetime(df[TS_COL], errors="coerce")
df = df.dropna(subset=[TS_COL]).sort_values(TS_COL)
df = df.drop_duplicates(subset=[TS_COL], keep="last")

# 3) Upewnij się, że kolumna celu nie ma NaN; ffill->bfill
if TARGET not in df.columns:
    raise ValueError(f"Brak kolumny celu {TARGET} w danych.")
df[TARGET] = df[TARGET].ffill().bfill()
df = df.dropna(subset=[TARGET])

# 4) Wyznacz kalendarzowe
df["hour"] = df[TS_COL].dt.hour
df["month"] = df[TS_COL].dt.month
df["weekday"] = df[TS_COL].dt.weekday
df["heating"] = ((df["month"] >= 10) | (df["month"] <= 3)).astype(int)

# 5) Suma opadu: jeśli brak, ustaw 0.0 (na test)
if "suma_opadu" not in df.columns:
    df["suma_opadu"] = 0.0
else:
    df["suma_opadu"] = df["suma_opadu"].fillna(0.0)

# 6) Lags/rolling względem przeszłości (per-wiersz do t-1h)
s = df.set_index(TS_COL)[TARGET].sort_index()

def build_row_at_ts(ts):
    row = {}
    # Kalendarz
    row["hour"] = ts.hour
    row["month"] = ts.month
    row["weekday"] = ts.weekday()
    row["heating"] = 1 if (row["month"] >= 10 or row["month"] <= 3) else 0
    # Opad: weź z najbliższego wiersza w danych (do ts)
    # (Jeśli nie znajdzie, ustaw 0.0)
    idx = df.index[df[TS_COL] == ts]
    if len(idx) > 0:
        row["suma_opadu"] = float(df.loc[idx[0], "suma_opadu"]) if pd.notna(df.loc[idx[0], "suma_opadu"]) else 0.0
    else:
        row["suma_opadu"] = 0.0
    # Lags & rolling z historii do ts-1h
    hist = s.loc[: ts - pd.Timedelta(hours=1)]
    if len(hist) < 3:
        return None  # za mało historii
    row["PM10_lag1"] = float(hist.iloc[-1])
    row["PM10_lag2"] = float(hist.iloc[-2])
    row["PM10_lag3"] = float(hist.iloc[-3])
    row["PM10_roll3"] = float(hist.iloc[-3:].mean())
    # Zwróć tylko cechy w kolejności z modelu
    return [row.get(f) for f in feats]

# 7) Test: weź ostatnie 24 timestampy i policz predykcję
last_ts = df[TS_COL].iloc[-24:]
X_rows = []
ts_list = []
for ts in last_ts:
    r = build_row_at_ts(ts)
    if r is not None and all(v is not None for v in r):
        X_rows.append(r)
        ts_list.append(ts)

if not X_rows:
    raise RuntimeError("Brak wierszy testowych (za mało historii).")

X_df = pd.DataFrame(X_rows, columns=feats)
yhat = model.predict(X_df)
print("Liczba unikalnych predykcji:", np.unique(yhat).size)
print("Predykcje (pierwsze ~10):", yhat[:10])
print("Średnia predykcji:", float(np.mean(yhat)))
print("Zakres:", float(np.min(yhat)), "->", float(np.max(yhat)))
