
# ⚠️ DEPRECATED (2026-09) — WAQI (aqicn.org) zabrania komercyjnego wykorzystania
# i redystrybucji danych na darmowym tokenie (zob. ToDo.md, sekcja "blokery
# sprzedaży"). Ten skrypt NIE jest już wywoływany przez run_full_pipeline.bat /
# run_pipeline_scheduled.bat / run_hourly.bat — GIOŚ (gios_fetch.py,
# gios_real_backfill.py) jest głównym, komercyjnie bezpiecznym źródłem
# pomiarów. Plik zostaje w repo wyłącznie dla zgodności z istniejącymi
# testami regresyjnymi (tests/test_fetchers_mocked.py) i jako dokumentacja
# poprzedniej architektury — nie uruchamiaj go w nowych wdrożeniach.

import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter, Retry
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

log_path = LOGS_DIR / f"waqi_{datetime.now():%Y%m%d}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger("waqi")

load_dotenv(BASE_DIR / ".env")
API_TOKEN = os.getenv("WAQI_TOKEN")
CITY = os.getenv("CITY", "Slupsk")
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "aqicn_slupsk_data.csv")

if not API_TOKEN:
    raise RuntimeError("Brak WAQI_TOKEN w .env – uzupełnij i spróbuj ponownie.")

URL = f"https://api.waqi.info/feed/{CITY}/?token={API_TOKEN}"

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1.0, status_forcelist=[429,500,502,503,504])))

def fetch() -> Dict[str, Any]:
    r = session.get(URL, timeout=25)
    r.raise_for_status()
    j = r.json()
    if j.get("status") != "ok":
        raise RuntimeError(f"Błąd API WAQI: {j.get('data')}")
    return j["data"]

def parse_to_row(data: Dict[str, Any]) -> pd.DataFrame:
    ts = data.get("time", {}).get("s")
    timestamp = pd.to_datetime(ts)
    aqi = data.get("aqi")
    iaqi = {k: v.get("v") for k, v in (data.get("iaqi", {}) or {}).items()}
    rename = {"pm25":"PM2.5","pm2_5":"PM2.5","pm10":"PM10","no2":"NO2","o3":"O3","t":"temperatura","h":"wilgotnosc_wzgledna","p":"cisnienie","w":"predkosc_wiatru"}
    parsed = {rename.get(k,k): v for k,v in iaqi.items()}
    row = {"timestamp": timestamp, "aqi": aqi, **parsed}
    df = pd.DataFrame([row])
    for c in ["aqi","PM2.5","PM10","NO2","O3","temperatura","wilgotnosc_wzgledna","cisnienie","predkosc_wiatru"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def _last_saved_ts(path: Path) -> pd.Timestamp | None:
    try:
        last = pd.read_csv(path, usecols=["timestamp"]).iloc[-1]["timestamp"]
        return pd.to_datetime(last)
    except Exception:
        return None

CANONICAL_COLUMNS = ["timestamp", "aqi", "wilgotnosc_wzgledna", "cisnienie", "PM10",
                      "temperatura", "predkosc_wiatru", "wg", "_backfilled"]


def main():
    try:
        data = fetch()
        df = parse_to_row(data)
        out = DATA_DIR / OUTPUT_FILE
        new_ts = df["timestamp"].iloc[0]
        if out.exists() and _last_saved_ts(out) == new_ts:
            logger.info(f"Duplikat timestamp {new_ts} – pomijam zapis.")
            return

        # KRYTYCZNE: kolejność kluczy w odpowiedzi WAQI (iaqi) nie jest gwarantowana
        # między wywołaniami — jeśli dopisalibyśmy df.to_csv(..., header=False) z
        # kolumnami w innej kolejności niż nagłówek pliku, wartości trafiłyby do
        # NIEWŁAŚCIWYCH kolumn (np. ciśnienie pod PM10) bez żadnego błędu. Dlatego
        # zawsze wyrównujemy kolumny do istniejącego nagłówka pliku (albo do stałej
        # kolejności kanonicznej przy tworzeniu nowego pliku) PRZED zapisem.
        if out.exists():
            existing_header = pd.read_csv(out, nrows=0).columns.tolist()
            target_columns = existing_header
        else:
            target_columns = CANONICAL_COLUMNS

        for col in target_columns:
            if col not in df.columns:
                df[col] = pd.NA
        df = df[target_columns]

        mode = "a" if out.exists() else "w"
        header = not out.exists()
        df.to_csv(out, mode=mode, header=header, index=False)
        logger.info(f"Dopisałem {len(df)} wiersz(e) do {out} (kolumny: {target_columns})")
    except Exception as e:
        logger.exception(f"Błąd pobierania WAQI: {e}")
        raise

if __name__ == "__main__":
    main()
