# -*- coding: utf-8 -*-
"""
build_merged_full.py — tworzy kompletny godzinowy dataset merged_hourly.csv.

Od refaktoryzacji licencyjnej (2026-09):
- Baza (oś czasu): siatka godzin zbudowana z realnych timestampów GIOŚ ∪ IMGW
  (bez zależności od płatnej/niekomercyjnej siatki Open-Meteo).
- PM10 / PM2.5 / NO2 / O3: z gios_slupsk.csv (match nearest 1h) — GIOŚ jest
  głównym źródłem pomiarów zanieczyszczeń.
- PM2.5 (uzupełniająco): z syngeos_agg.csv, tam gdzie brak GIOŚ.
- Kolumny pogodowe: z imgw_synop_hourly.csv (match nearest 1h); krótkie luki
  (do 6h) są interpolowane liniowo, bo nie ma już Open-Meteo do wypełniania.

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

WEATHER_COLS = ["temperatura", "predkosc_wiatru", "wilgotnosc_wzgledna", "suma_opadu", "cisnienie"]
POLLUTANT_COLS = ["PM10", "PM2.5", "NO2", "O3"]


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
    gios_path = DATA / "gios_slupsk.csv"
    syngeos_path = DATA / "syngeos_agg.csv"
    out_path = DATA / "merged_hourly.csv"

    imgw = read_ts(imgw_path)
    gios = read_ts(gios_path).sort_values("timestamp") if gios_path.exists() else pd.DataFrame()

    if gios.empty and imgw.empty:
        logger.error("Brak danych GIOŚ i IMGW — uruchom najpierw gios_real_backfill.py / imgw_fetch.py")
        return

    # --- Baza: siatka pełnych godzin z realnego zakresu GIOŚ ∪ IMGW (bez Open-Meteo) ---
    ts_candidates = [df["timestamp"] for df in (imgw, gios) if not df.empty]
    ts_min = min(s.min() for s in ts_candidates)
    ts_max = max(s.max() for s in ts_candidates)
    base = pd.DataFrame({"timestamp": pd.date_range(ts_min.floor("h"), ts_max.ceil("h"), freq="h")})
    logger.info(f"Baza (GIOŚ ∪ IMGW): {len(base)} godzin ({ts_min} – {ts_max})")

    merged = base.copy()

    # --- Pogoda z IMGW (nearest, tolerancja 1h) ---
    if not imgw.empty:
        imgw_cols = [c for c in WEATHER_COLS if c in imgw.columns]
        imgw_w = imgw[["timestamp"] + imgw_cols].sort_values("timestamp").drop_duplicates("timestamp")
        merged = pd.merge_asof(
            merged.sort_values("timestamp"), imgw_w,
            on="timestamp", direction="nearest", tolerance=pd.Timedelta("1h")
        )
        # Krótkie luki (do 6h) interpolujemy liniowo — nie ma już Open-Meteo do wypełniania.
        for col in imgw_cols:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").interpolate(method="linear", limit=6)
        logger.info(f"Pogoda z IMGW: {merged[imgw_cols[0]].notna().sum() if imgw_cols else 0} godzin uzupełnionych")
    else:
        logger.warning("Brak danych IMGW — kolumny pogodowe będą puste")

    # --- Zanieczyszczenia z GIOŚ (nearest, tolerancja 1h) ---
    if not gios.empty:
        gios_cols = [c for c in POLLUTANT_COLS if c in gios.columns]
        gios_p = gios[["timestamp"] + gios_cols].sort_values("timestamp").drop_duplicates("timestamp")
        merged = pd.merge_asof(
            merged.sort_values("timestamp"), gios_p,
            on="timestamp", direction="nearest", tolerance=pd.Timedelta("1h")
        )
        logger.info(f"Po złączeniu z GIOŚ: {merged['PM10'].notna().sum() if 'PM10' in merged.columns else 0} godzin z PM10")
    else:
        logger.warning("Brak danych GIOŚ")

    for col in POLLUTANT_COLS:
        if col not in merged.columns:
            merged[col] = pd.NA
        merged[col] = pd.to_numeric(merged[col], errors="coerce")

    # --- PM2.5 (uzupełniająco) z Syngeos, tam gdzie brak GIOŚ ---
    sg = read_ts(syngeos_path)
    if not sg.empty and "timestamp" in sg.columns:
        sg = sg.sort_values("timestamp")
        pm_cols = [c for c in ["pm25_mean", "pm25_median", "pm10_mean", "pm10_median"] if c in sg.columns]
        if pm_cols:
            merged = pd.merge_asof(
                merged.sort_values("timestamp"),
                sg[["timestamp"] + pm_cols].sort_values("timestamp"),
                on="timestamp", direction="nearest", tolerance=pd.Timedelta("1h")
            )
            if "pm25_mean" in merged.columns:
                merged["PM2.5"] = merged["PM2.5"].fillna(pd.to_numeric(merged["pm25_mean"], errors="coerce"))
            if "pm10_mean" in merged.columns:
                merged["PM10"] = merged["PM10"].fillna(pd.to_numeric(merged["pm10_mean"], errors="coerce"))
            logger.info("Dołączono Syngeos: uzupełniono PM2.5/PM10 tam, gdzie brakowało pomiarów GIOŚ")

    merged = merged.sort_values("timestamp").reset_index(drop=True)
    merged.to_csv(out_path, index=False)
    logger.info(
        f"Zapisano {len(merged)} wierszy do {out_path} "
        f"(z PM10: {merged['PM10'].notna().sum()}, bez PM10: {merged['PM10'].isna().sum()})"
    )


if __name__ == "__main__":
    main()
