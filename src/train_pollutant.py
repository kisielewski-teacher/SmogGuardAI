
# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import sys
import logging
from datetime import datetime
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
import joblib

# ──────────────────────────────────────────────────────────────────────────────
# Import wspólnych ścieżek (DATA_DIR + pliki) z roota projektu
# ──────────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from data_paths import (
    DATA_DIR, MERGED_HOURLY_CSV, AQICN_HIST_CSV,
    AIRLY_CSV, SENSOR_COMMUNITY_CSV, GIOS_CSV
)

MODELS_DIR = ROOT / "models"
LOGS_DIR   = ROOT / "logs"
MODELS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# Pomocnicze: mapowanie nazw, wykrywanie timestamp/target
# ──────────────────────────────────────────────────────────────────────────────
def sanitize_name(target: str) -> str:
    mapping = {"PM10": "pm10", "PM2.5": "pm25", "NO2": "no2", "O3": "o3"}
    return mapping.get(target, target.lower().replace(".", "").replace(" ", ""))

def target_synonyms(target: str) -> list[str]:
    """Synonimy nazw kolumn dla poszczególnych parametrów (różne źródła)."""
    t = target.upper()
    if t == "PM10":
        return ["PM10", "pm10", "P1"]
    if t in ("PM2.5", "PM25"):
        return ["PM2.5", "PM25", "pm25", "PM2_5", "P2"]
    if t == "NO2":
        return ["NO2", "NO₂", "no2", "nitrogen_dioxide"]
    if t == "O3":
        return ["O3", "O₃", "o3", "ozone"]
    return [target]

def resolve_timestamp_col(df: pd.DataFrame) -> str:
    for cand in ["timestamp", "time", "Time", "Data", "date", "datetime"]:
        if cand in df.columns:
            return cand
    raise RuntimeError("Nie znaleziono kolumny czasu (szukano: timestamp/time/Data/date/datetime).")

def find_target_column(df: pd.DataFrame, target: str) -> str | None:
    syns = target_synonyms(target)
    # bezpośrednie dopasowanie
    for s in syns:
        if s in df.columns:
            return s
    # dopasowanie case-insensitive
    lower_map = {c.lower(): c for c in df.columns}
    for s in syns:
        if s.lower() in lower_map:
            return lower_map[s.lower()]
    return None

def read_and_normalize(path: Path, target: str) -> tuple[pd.DataFrame, str]:
    """
    Wczytuje CSV, wykrywa i normalizuje kolumnę czasu do 'timestamp',
    znajduje właściwą kolumnę dla targetu (synonimy) i zwraca (df, target_col).
    """
    df = pd.read_csv(path)
    ts_col = resolve_timestamp_col(df)
    df["timestamp"] = pd.to_datetime(df[ts_col], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    df = df.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)

    tgt_col = find_target_column(df, target)
    if tgt_col is None:
        raise FileNotFoundError(
            f"Plik {path} nie zawiera kolumny dla '{target}'. "
            f"Znalezione kolumny: {list(df.columns)}"
        )
    return df, tgt_col

# ──────────────────────────────────────────────────────────────────────────────
# Składanie serii docelowej z wielu źródeł
# ──────────────────────────────────────────────────────────────────────────────
def build_target_series(target: str) -> pd.DataFrame:
    """
    Buduje serię docelową (timestamp + target) z dostępnych źródeł:
    priorytet: merged_hourly -> GIOS -> WAQI (legacy) -> Airly -> Sensor.Community.
    Dane są zaokrąglane do godziny; przy duplikatach stosujemy średnią.
    """
    candidates = []
    for path in [MERGED_HOURLY_CSV, GIOS_CSV, AQICN_HIST_CSV, AIRLY_CSV, SENSOR_COMMUNITY_CSV]:
        if path.exists():
            try:
                df, tgt = read_and_normalize(path, target)
                d = df[["timestamp", tgt]].copy()
                d[tgt] = pd.to_numeric(d[tgt], errors="coerce")
                # ujednolicenie do godzin
                d["timestamp"] = d["timestamp"].dt.floor("h")
                d = d.groupby("timestamp", as_index=False)[tgt].mean()
                candidates.append((path, d, tgt))
            except FileNotFoundError:
                # ten plik po prostu nie ma kolumny dla targetu – ignorujemy
                continue

    if not candidates:
        raise FileNotFoundError(
            f"Nie znaleziono żadnego źródła z kolumną '{target}'. "
            f"Sprawdź dostępność i nagłówki plików w DATA_DIR."
        )

    # priorytet źródeł
    priority = [MERGED_HOURLY_CSV, GIOS_CSV, AQICN_HIST_CSV, AIRLY_CSV, SENSOR_COMMUNITY_CSV]
    def sort_key(item):  # item = (path, df, tgt)
        try:
            return priority.index(item[0])
        except ValueError:
            return 999

    candidates.sort(key=sort_key)

    # sklejanie przez combine_first (pierwsze źródło ma najwyższy priorytet)
    combined = None
    for path, d, tgt in candidates:
        s = d.set_index("timestamp")[tgt]
        if combined is None:
            combined = s
        else:
            combined = combined.combine_first(s)

    final = combined.sort_index().dropna()
    res = final.reset_index()
    res.columns = ["timestamp", target]
    return res

# ──────────────────────────────────────────────────────────────────────────────
# Budowa cech i trening
# ──────────────────────────────────────────────────────────────────────────────
def build_features(df: pd.DataFrame, target_name: str) -> pd.DataFrame:
    """
    Cechy: hour, dow, lag1/lag3, rolling3/rolling6 oparte o target_name.
    Cel zapisujemy jako 'TARGET' (spójnie z treningiem).
    """
    name = sanitize_name(target_name)
    df = df.copy()
    # cechy czasowe
    df["hour"] = df["timestamp"].dt.hour
    df["dow"]  = df["timestamp"].dt.day_of_week
    # lagi i rolling
    df[f"{name}_lag1"]  = df[target_name].shift(1)
    df[f"{name}_lag3"]  = df[target_name].shift(3)
    df[f"{name}_roll3"] = df[target_name].rolling(3).mean().shift(1)
    df[f"{name}_roll6"] = df[target_name].rolling(6).mean().shift(1)
    # wymagamy lag1 i roll3
    feats = df.dropna(subset=[f"{name}_lag1", f"{name}_roll3"]).copy()
    feats["TARGET"] = df[target_name]
    return feats

def main(target: str = "PM10"):
    name = sanitize_name(target)
    log_path = LOGS_DIR / f"train_{name}_{datetime.now():%Y%m%d}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()]
    )
    logger = logging.getLogger("train")

    # 1) Zbuduj serię docelową z dostępnych plików
    series_df = build_target_series(target)  # -> kolumny: timestamp, <target>
    logger.info(f"Zbudowano serię dla {target}: wierszy={len(series_df)}")

    # 2) Cecha-inżynieria
    feats = build_features(series_df, target)
    if feats.empty:
        raise RuntimeError("Po zbudowaniu cech nie pozostały wiersze. Dodaj więcej historii.")
    FEATURES_CSV = DATA_DIR / f"features_{name}.csv"
    feats.to_csv(FEATURES_CSV, index=False)
    logger.info(f"Wygenerowano cechy: {FEATURES_CSV} (wierszy: {len(feats)})")

    # 3) Trening i walidacja czasowa
    y = feats["TARGET"].astype(float)
    X = feats.drop(columns=["TARGET", "timestamp"])

    ts = TimeSeriesSplit(n_splits=4)
    scores = []
    for tr_idx, te_idx in ts.split(X):
        m = RandomForestRegressor(n_estimators=300, random_state=42, n_jobs=-1)
        m.fit(X.iloc[tr_idx], y.iloc[tr_idx])
        pred = m.predict(X.iloc[te_idx])
        rmse = float(np.sqrt(mean_squared_error(y.iloc[te_idx], pred)))
        scores.append(rmse)
    rmse_avg = float(np.mean(scores))
    logger.info(f"Średni RMSE (TimeSeriesSplit): {rmse_avg:.2f}")

    # 4) Finalny model + zapis
    model = RandomForestRegressor(n_estimators=300, random_state=42, n_jobs=-1)
    model.fit(X, y)
    MODEL_PATH = MODELS_DIR / f"{name}_rf.pkl"
