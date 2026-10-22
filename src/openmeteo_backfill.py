# -*- coding: utf-8 -*-
"""
⚠️ DEPRECATED (2026-09) — darmowy poziom Open-Meteo jest licencjonowany
wyłącznie na użycie niekomercyjne (zob. TODO.md, sekcja "blokery sprzedaży").
Ten skrypt NIE jest już wywoływany przez run_full_pipeline.bat /
run_pipeline_scheduled.bat / run_hourly.bat. build_merged_full.py buduje
siatkę godzin samodzielnie (GIOŚ ∪ IMGW) i uzupełnia krótkie luki pogodowe
interpolacją zamiast Open-Meteo. Plik zostaje w repo wyłącznie dla zgodności
z istniejącymi testami regresyjnymi (tests/test_bugfixes.py) — nie uruchamiaj
go w nowych wdrożeniach bez wykupienia licencji komercyjnej Open-Meteo.

openmeteo_backfill.py — uzupełnia luki w danych pogodowych z Open-Meteo (darmowe, bez klucza).

Strategia:
1. Wczytaj istniejące aqicn_slupsk_data.csv i imgw_synop_hourly.csv.
2. Wyznacz pełny zakres godzin (od pierwszego do ostatniego rekordu WAQI).
3. Pobierz z Open-Meteo historyczne dane godzinowe dla Słupska.
4. Uzupełnij kolumny pogodowe w aqicn tylko tam, gdzie ich brak.
5. Uzupełnij imgw_synop_hourly o godziny których brakuje (jako stacja "OpenMeteo-Slupsk").
"""
from pathlib import Path
import pandas as pd
import requests
import logging
from datetime import datetime

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
LOGS = BASE / "logs"
LOGS.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOGS / f"openmeteo_{datetime.now():%Y%m%d}.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("openmeteo")

LAT = 54.4639
LON = 17.0287
OM_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_openmeteo(start: str, end: str) -> pd.DataFrame:
    params = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": start,
        "end_date": end,
        "hourly": "temperature_2m,relativehumidity_2m,surface_pressure,windspeed_10m,precipitation",
        "timezone": "Europe/Warsaw",
        "wind_speed_unit": "ms",
    }
    r = requests.get(OM_URL, params=params, timeout=60)
    r.raise_for_status()
    j = r.json()
    h = j["hourly"]
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(h["time"]).tz_localize(None),
        "temperatura": h["temperature_2m"],
        "wilgotnosc_wzgledna": h["relativehumidity_2m"],
        "cisnienie": h["surface_pressure"],
        "predkosc_wiatru": h["windspeed_10m"],
        "suma_opadu": h["precipitation"],
    })
    logger.info(f"Open-Meteo: {len(df)} godzin ({start} – {end})")
    return df


def fill_waqi_weather(waqi_path: Path, om: pd.DataFrame) -> None:
    df = pd.read_csv(waqi_path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

    weather_cols = ["temperatura", "wilgotnosc_wzgledna", "cisnienie", "predkosc_wiatru"]
    existing_cols = [c for c in weather_cols if c in df.columns]

    om_idx = om.set_index("timestamp")

    filled = 0
    for col in existing_cols:
        mask = df[col].isna()
        if mask.any():
            vals = df.loc[mask, "timestamp"].map(om_idx[col])
            df.loc[mask, col] = vals.values
            filled += mask.sum()

    df.to_csv(waqi_path, index=False)
    logger.info(f"aqicn_slupsk_data.csv: uzupełniono {filled} brakujących wartości pogodowych")


def fill_imgw(imgw_path: Path, om: pd.DataFrame) -> None:
    if imgw_path.exists():
        existing = pd.read_csv(imgw_path)
        existing_cols = list(existing.columns)
        def _parse(s):
            try:
                t = pd.Timestamp(s)
                return t.tz_localize(None) if t.tzinfo is None else t.tz_convert("Europe/Warsaw").tz_localize(None)
            except Exception:
                return pd.NaT
        existing["timestamp"] = existing["timestamp"].apply(_parse)
        existing_ts = set(existing["timestamp"].dropna())
    else:
        existing = pd.DataFrame()
        existing_cols = None
        existing_ts = set()

    new_rows = om[~om["timestamp"].isin(existing_ts)].copy()
    new_rows.insert(0, "stacja", "OpenMeteo-Slupsk")

    if new_rows.empty:
        logger.info("imgw_synop_hourly.csv: brak nowych godzin do dodania")
        return

    if existing.empty:
        new_rows.to_csv(imgw_path, index=False)
    else:
        # Dopasuj kolejność kolumn do prawdziwego nagłówka pliku przed doklejeniem
        # bez nagłówka — inaczej pandas zapisuje wartości pozycyjnie i (gdy kolejność
        # się różni od tej budowanej w fetch_openmeteo()) po cichu miesza kolumny
        # pogodowe (np. wilgotność ląduje pod nagłówkiem prędkości wiatru).
        new_rows = new_rows.reindex(columns=existing_cols)
        new_rows.to_csv(imgw_path, mode="a", header=False, index=False)

    logger.info(f"imgw_synop_hourly.csv: dodano {len(new_rows)} nowych godzin z Open-Meteo")


def main():
    waqi_path = DATA / "aqicn_slupsk_data.csv"
    imgw_path = DATA / "imgw_synop_hourly.csv"

    df_waqi = pd.read_csv(waqi_path, parse_dates=["timestamp"])
    start_date = df_waqi["timestamp"].min().strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    logger.info(f"Pobieram Open-Meteo: {start_date} – {end_date}")
    om = fetch_openmeteo(start_date, end_date)

    fill_waqi_weather(waqi_path, om)
    fill_imgw(imgw_path, om)
    logger.info("Backfill zakończony.")


if __name__ == "__main__":
    main()
