
# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
from collections import deque
import sys
import numpy as np
import pandas as pd
import joblib
from datetime import timedelta

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from data_paths import (
    DATA_DIR, MERGED_HOURLY_CSV, AQICN_HIST_CSV,
    FORECAST_PM10_CSV, FORECAST_PM25_CSV, FORECAST_NO2_CSV, FORECAST_O3_CSV,
    PM10_LATEST_CSV
)

def sanitize_name(target: str) -> str:
    return {"PM10": "pm10", "PM2.5": "pm25", "NO2": "no2", "O3": "o3"}[target]

def pick_source_csv(target: str) -> pd.DataFrame:
    # Preferuj merged_hourly jeśli ma target; inaczej WAQI historia
    if MERGED_HOURLY_CSV.exists():
        dfm = pd.read_csv(MERGED_HOURLY_CSV)
        if target in dfm.columns:
            return dfm
    if AQICN_HIST_CSV.exists():
        dfh = pd.read_csv(AQICN_HIST_CSV)
        if target in dfh.columns:
            return dfh
    raise FileNotFoundError(f"Brak kolumny '{target}' w {MERGED_HOURLY_CSV} i {AQICN_HIST_CSV}.")

def parse_clean(dfm: pd.DataFrame, target: str) -> pd.DataFrame:
    if "timestamp" not in dfm.columns:
        raise RuntimeError("Brak kolumny 'timestamp'.")
    dfm = dfm.copy()
    dfm["timestamp"] = pd.to_datetime(dfm["timestamp"], errors="coerce")
    dfm = dfm.dropna(subset=["timestamp"]).sort_values("timestamp")
    dfm = dfm.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)
    if target not in dfm.columns:
        raise RuntimeError(f"Brak kolumny '{target}'.")
    dfm[target] = pd.to_numeric(dfm[target], errors="coerce")
    return dfm

def build_features(dfm: pd.DataFrame, target: str) -> pd.DataFrame:
    name = sanitize_name(target)
    dfm = dfm.copy()
    dfm["hour"] = dfm["timestamp"].dt.hour
    dfm["dow"] = dfm["timestamp"].dt.dayofweek
    dfm[f"{name}_lag1"] = dfm[target].shift(1)
    dfm[f"{name}_lag3"] = dfm[target].shift(3)
    dfm[f"{name}_roll3"] = dfm[target].rolling(3).mean().shift(1)
    dfm[f"{name}_roll6"] = dfm[target].rolling(6).mean().shift(1)
    feats = dfm.dropna(subset=[f"{name}_lag1", f"{name}_roll3"]).copy()
    feats["TARGET"] = dfm[target]
    return feats

def load_X_space(target: str) -> tuple[list[str], pd.Series]:
    name = sanitize_name(target)
    feats_csv = DATA_DIR / f"features_{name}.csv"
    if not feats_csv.exists():
        raise FileNotFoundError(f"Brak {feats_csv}. Uruchom najpierw trening dla {target}.")
    df_feat = pd.read_csv(feats_csv)
    X_cols = [c for c in df_feat.columns if c not in ("TARGET", "timestamp")]
    col_means = df_feat[X_cols].mean(numeric_only=True)
    return X_cols, col_means

def align_X(df_feats: pd.DataFrame, X_cols: list[str], col_means: pd.Series) -> pd.DataFrame:
    X = df_feats.reindex(columns=X_cols)
    for c in X_cols:
        if X[c].isna().any():
            X[c] = X[c].fillna(col_means.get(c, 0.0))
    return X.infer_objects(copy=False)

def forecast_path(target: str) -> Path:
    return {
        "PM10": FORECAST_PM10_CSV,
        "PM2.5": FORECAST_PM25_CSV,
        "NO2": FORECAST_NO2_CSV,
        "O3": FORECAST_O3_CSV,
    }[target]

def main(target: str = "PM10", horizon_hours: int = 24, hist_fc_hours: int = 24):
    name = sanitize_name(target)
    model_path = ROOT / "models" / f"{name}_rf.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"Brak modelu: {model_path}. Uruchom trening dla {target}.")

    model = joblib.load(model_path)

    # dane źródłowe
    df_src = pick_source_csv(target)
    df_src = parse_clean(df_src, target)

    # cechy jak w treningu
    feats_hist = build_features(df_src, target)
    if feats_hist.empty:
        raise RuntimeError("Brak wystarczających cech z historii.")

    # przestrzeń cech z treningu
    X_cols, col_means = load_X_space(target)
    X_hist = align_X(feats_hist, X_cols, col_means)

    # predykcja historii
    y_hist = feats_hist["TARGET"].astype(float)
    y_hist_pred = model.predict(X_hist)
    hist_out = feats_hist[["timestamp"]].copy()
    hist_out[f"{name}_true"] = y_hist
    hist_out[f"{name}_hist"] = y_hist_pred
    hist_out["error"] = hist_out[f"{name}_hist"] - hist_out[f"{name}_true"]

    # przyszłość: rekurencyjne uaktualnianie lag/rolling
    last_ts = feats_hist["timestamp"].max()
    series = df_src.sort_values("timestamp")[target].dropna().tolist()
    win = deque(series[-6:], maxlen=6)

    fut_rows = []
    fut_preds, fut_ts = [], []
    for h in range(1, horizon_hours + 1):
        ts = last_ts + timedelta(hours=h)
        lag1 = win[-1] if len(win) >= 1 else np.nan
        lag3 = win[-3] if len(win) >= 3 else np.nan
        roll3 = np.mean(list(win)[-3:]) if len(win) >= 3 else (np.mean(list(win)) if len(win) > 0 else np.nan)
        roll6 = np.mean(list(win)) if len(win) >= 1 else np.nan

        row = {
            "timestamp": ts, "hour": ts.hour, "dow": ts.weekday(),
            f"{name}_lag1": lag1, f"{name}_lag3": lag3,
            f"{name}_roll3": roll3, f"{name}_roll6": roll6,
        }
        X_step = align_X(pd.DataFrame([row]), X_cols, col_means)
        y_hat = float(model.predict(X_step)[0])
        fut_preds.append(y_hat)
        fut_ts.append(ts)
        win.append(y_hat)

    future_out = pd.DataFrame({"timestamp": fut_ts, f"{name}_pred": fut_preds})

    # forecast = historia (ostatnie Nh) + przyszłość (z nazwą *_pred)
    hist_fc = hist_out.dropna(subset=[f"{name}_hist"]).copy()
    last_ts_hist = hist_fc["timestamp"].max()
    hist_fc = hist_fc[hist_fc["timestamp"] >= last_ts_hist - pd.Timedelta(hours=hist_fc_hours)]
    hist_fc = hist_fc[["timestamp", f"{name}_hist"]].rename(columns={f"{name}_hist": f"{name}_pred"})

    fc_combined = pd.concat([hist_fc, future_out], ignore_index=True)
    fc_combined = fc_combined.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")

    # zapis forecastu
    FC_PATH = forecast_path(target)
    FC_PATH.parent.mkdir(parents=True, exist_ok=True)
    fc_combined.to_csv(FC_PATH, index=False)
    print(f"[OK] Zapisano forecast ({target}): {FC_PATH}")

    # PM10: dodatkowy plik dla dashboardu
    if target == "PM10":
        PM10_LATEST_CSV.parent.mkdir(parents=True, exist_ok=True)
        pm10_all = pd.merge(
            hist_out.rename(columns={f"{name}_true": "pm10_true", f"{name}_hist": "pm10_hist"}),
            future_out.rename(columns={f"{name}_pred": "pm10_pred"}),
            on="timestamp", how="outer"
        ).sort_values("timestamp")
        pm10_all.to_csv(PM10_LATEST_CSV, index=False)
        print(f"[OK] Zapisano łączony plik PM10: {PM10_LATEST_CSV}")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--target", type=str, default="PM10", choices=["PM10", "PM2.5", "NO2", "O3"])
    p.add_argument("--horizon", type=int, default=24)
    p.add_argument("--hist-hours", type=int, default=24)
    args = p.parse_args()
    main(target=args.target, horizon_hours=args.horizon, hist_fc_hours=args.hist_hours)
