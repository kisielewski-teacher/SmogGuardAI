# -*- coding: utf-8 -*-
"""
build_merged_full.py — tworzy kompletny godzinowy dataset merged_hourly_full.csv.

Strategia:
- Baza: pełna siatka godzin z Open-Meteo (imgw_synop_hourly.csv, stacja=OpenMeteo-Slupsk)
- PM10: z aqicn_slupsk_data.csv (match nearest 1h)
- PM25: z syngeos_agg.csv (match nearest 1h)
- Kolumny pogodowe: bezpośrednio z Open-Meteo

Wyjście: data/merged_hourly.csv (zastępuje plik — ten plik jest wejściem do features.py)
"""
from pathlib import Path
import pandas as pd
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
        logging.FileHandler(LOGS / f"build_merged_{datetime.now():%Y%m%d}.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("build_merged")


def _parse_ts(s):
    try:
        t = pd.Timestamp(s)
        return t.tz_localize(None) if t.tzinfo is None else t.tz_convert("Europe/Warsaw").tz_localize(None)
    except Exception:
        return pd.NaT


def read_ts(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "timestamp" in df.columns:
        df["timestamp"] = df["timestamp"].apply(_parse_ts)
        df = df.dropna(subset=["timestamp"])
    return df


def main():
    imgw_path = DATA / "imgw_synop_hourly.csv"
    waqi_path = DATA / "aqicn_slupsk_data.csv"
    syngeos_path = DATA / "syngeos_agg.csv"
    out_path = DATA / "merged_hourly.csv"

    # --- Baza: Open-Meteo godziny (stacja OpenMeteo-Slupsk) ---
    imgw = read_ts(imgw_path)
    om = imgw[imgw["stacja"] == "OpenMeteo-Slupsk"].copy()
    if om.empty:
        logger.error("Brak danych OpenMeteo-Slupsk w imgw_synop_hourly.csv — uruchom openmeteo_backfill.py")
        return

    om = om.sort_values("timestamp").drop_duplicates("timestamp")
    logger.info(f"Baza Open-Meteo: {len(om)} godzin ({om['timestamp'].min()} – {om['timestamp'].max()})")

    # Rename do standardowych nazw w merged
    base = om[["timestamp", "temperatura", "predkosc_wiatru", "wilgotnosc_wzgledna", "suma_opadu", "cisnienie"]].copy()
    base.rename(columns={
        "temperatura": "temperatura_y",
        "predkosc_wiatru": "predkosc_wiatru_y",
        "wilgotnosc_wzgledna": "wilgotnosc_wzgledna_y",
        "cisnienie": "cisnienie_y",
    }, inplace=True)

    # --- PM10 z WAQI (merge_asof nearest 1h) ---
    waqi = read_ts(waqi_path).sort_values("timestamp")
    if not waqi.empty:
        waqi_pm = waqi[["timestamp", "PM10", "aqi",
                         "temperatura", "wilgotnosc_wzgledna", "cisnienie", "predkosc_wiatru"]].copy()
        waqi_pm.rename(columns={
            "PM10": "PM10_x",
            "temperatura": "temperatura_x",
            "wilgotnosc_wzgledna": "wilgotnosc_wzgledna_x",
            "cisnienie": "cisnienie_x",
            "predkosc_wiatru": "predkosc_wiatru_x",
        }, inplace=True)
        merged = pd.merge_asof(
            base.sort_values("timestamp"),
            waqi_pm.sort_values("timestamp"),
            on="timestamp", direction="nearest", tolerance=pd.Timedelta("1h")
        )
        logger.info(f"Po złączeniu z WAQI: {merged['PM10_x'].notna().sum()} godzin z PM10")
    else:
        merged = base.copy()
        logger.warning("Brak danych WAQI")

    # Stwórz kanoniczną kolumnę PM10 (priorytet: WAQI)
    merged["PM10"] = pd.to_numeric(merged.get("PM10_x"), errors="coerce")

    # Uzupełnij pogodę: gdzie brak WAQI, użyj Open-Meteo
    for col_x, col_y in [
        ("temperatura_x", "temperatura_y"),
        ("wilgotnosc_wzgledna_x", "wilgotnosc_wzgledna_y"),
        ("cisnienie_x", "cisnienie_y"),
        ("predkosc_wiatru_x", "predkosc_wiatru_y"),
    ]:
        if col_x not in merged.columns:
            merged[col_x] = merged[col_y]
        else:
            merged[col_x] = merged[col_x].fillna(merged[col_y])

    # --- PM25 z Syngeos (merge_asof nearest 1h) ---
    sg = read_ts(syngeos_path)
    if not sg.empty and "timestamp" in sg.columns:
        sg = sg.sort_values("timestamp")
        pm25_cols = [c for c in ["pm25_mean", "pm25_median", "pm10_mean", "pm10_median"] if c in sg.columns]
        merged = pd.merge_asof(
            merged.sort_values("timestamp"),
            sg[["timestamp"] + pm25_cols].sort_values("timestamp"),
            on="timestamp", direction="nearest", tolerance=pd.Timedelta("1h")
        )
        # Uzupełnij PM10 z syngeos gdzie brak WAQI
        if "pm10_mean" in merged.columns:
            merged["PM10"] = merged["PM10"].fillna(pd.to_numeric(merged["pm10_mean"], errors="coerce"))
        logger.info(f"Po złączeniu z Syngeos: {merged['PM10'].notna().sum()} godzin z PM10")

    # Zachowaj kompatybilność z merge_hourly.csv (kolumna PM10 jako ostatnia)
    merged = merged.sort_values("timestamp").reset_index(drop=True)
    merged.to_csv(out_path, index=False)
    logger.info(
        f"Zapisano {len(merged)} wierszy do {out_path} "
        f"(z PM10: {merged['PM10'].notna().sum()}, bez PM10: {merged['PM10'].isna().sum()})"
    )


if __name__ == "__main__":
    main()
