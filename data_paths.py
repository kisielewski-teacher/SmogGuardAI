
# data_paths.py
from __future__ import annotations
import os, time
from pathlib import Path
from typing import Optional

# Czytamy konfigurację katalogu danych:
# 1) Zmienna ENV DATA_DIR, 2) Streamlit secrets['DATA_DIR'], 3) <ROOT>/data
def project_root() -> Path:
    return Path(__file__).resolve().parent

def resolve_data_dir() -> Path:
    env_dir = os.environ.get("DATA_DIR")
    if env_dir:
        p = Path(env_dir).expanduser().resolve()
    else:
        try:
            import streamlit as st
            data_dir_name = st.secrets.get("DATA_DIR", "data")
        except Exception:
            data_dir_name = "data"
        p = (project_root() / data_dir_name).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p

DATA_DIR: Path = resolve_data_dir()

# --- Stałe ze wspólnymi plikami (dopasowane do obu aplikacji) ---
AQICN_HIST_CSV        = DATA_DIR / "aqicn_slupsk_data.csv"
MERGED_HOURLY_CSV     = DATA_DIR / "merged_hourly.csv"

FORECAST_PM10_CSV     = DATA_DIR / "forecast_pm10.csv"
FORECAST_PM25_CSV     = DATA_DIR / "forecast_pm25.csv"
FORECAST_NO2_CSV      = DATA_DIR / "forecast_no2.csv"
FORECAST_O3_CSV       = DATA_DIR / "forecast_o3.csv"

AIRLY_CSV             = DATA_DIR / "airly_slupsk.csv"
SENSOR_COMMUNITY_CSV  = DATA_DIR / "sensor_community_slupsk.csv"
GIOS_CSV              = DATA_DIR / "gios_slupsk.csv"

# Dashboard PM10 (plik łączony historii i prognoz):
PM10_LATEST_CSV       = DATA_DIR / "pm10_all_latest.csv"

# --- Helpery ---
def file_mtime(p: Path) -> Optional[float]:
    try:
        return p.stat().st_mtime
    except FileNotFoundError:
        return None

def fmt_ts(ts: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "brak pliku"

def find_latest(glob_pattern: str) -> Optional[Path]:
    import glob
    files = [Path(f) for f in glob.glob(glob_pattern)]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]
