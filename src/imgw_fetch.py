
import os
import logging
from pathlib import Path
from datetime import datetime
import argparse

import pandas as pd
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

log_path = LOGS_DIR / f"imgw_{datetime.now():%Y%m%d}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger("imgw")

load_dotenv(BASE_DIR / ".env")
stations_str = os.getenv("IMGW_STATIONS", "Slupsk,Koszalin,Chojnice,Ustka,Leba")
stations = [s.strip() for s in stations_str.split(",") if s.strip()]

URL = "https://danepubliczne.imgw.pl/api/data/synop"

def fetch_imgw():
    r = requests.get(URL, timeout=25)
    r.raise_for_status()
    return r.json()

def normalize(df: pd.DataFrame, stations_filter: list[str] | None = None) -> pd.DataFrame:
    """Normalize API JSON -> hourly table filtered by station names (case-insensitive, substring match).

    If ``stations_filter`` is None the global `stations` from env/default is used.
    """
    filter_list = stations_filter or stations
    if "stacja" not in df.columns:
        # fallback: return full normalized table if schema unexpected
        near = df.copy()
    else:
        # substring, case-insensitive match for each requested station
        if filter_list:
            upper_filters = [f.upper() for f in filter_list]
            mask = df["stacja"].astype(str).str.upper().apply(
                lambda name: any(filt in name for filt in upper_filters)
            )
            near = df[mask].copy()
        else:
            near = df.copy()

    # Uwaga: timestamp bez strefy (naive)
    near["timestamp"] = pd.to_datetime(
        near.get("data_pomiaru", "") + " " + near.get("godzina_pomiaru", "").astype(str).str.zfill(2) + ":00:00",
        errors="coerce"
    )
    cols = [
        "stacja", "timestamp", "temperatura", "predkosc_wiatru", "kierunek_wiatru",
        "wilgotnosc_wzgledna", "suma_opadu", "cisnienie"
    ]
    out = near[[c for c in cols if c in near.columns]].copy()
    for c in ["temperatura", "predkosc_wiatru", "kierunek_wiatru", "wilgotnosc_wzgledna", "suma_opadu", "cisnienie"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out

def append_aligned(norm: pd.DataFrame, out: Path) -> None:
    """Dopisz wiersze tak, zeby kolumny zgadzaly sie z naglowkiem pliku (inaczej CSV sie rozjezdza).

    Gdy plik nie ma jeszcze jakiejs nowej kolumny (np. kierunek_wiatru), przepisujemy go z pusta kolumna.
    """
    if not out.exists() or out.stat().st_size == 0:
        norm.to_csv(out, index=False)
        return
    old = pd.read_csv(out)
    missing = [c for c in norm.columns if c not in old.columns]
    if missing:
        pd.concat([old, norm], ignore_index=True).to_csv(out, index=False)
        return
    norm.reindex(columns=list(old.columns)).to_csv(out, mode="a", header=False, index=False)


def main():
    ap = argparse.ArgumentParser(prog="imgw_fetch.py", description="Fetch IMGW synop and save hourly rows (filter by station).")
    ap.add_argument("--station", "-s", help="Station name or comma-separated names (substring match, case-insensitive)")
    ap.add_argument("--out", "-o", default=str(DATA_DIR / "imgw_synop_hourly.csv"), help="Output CSV path (default: data/imgw_synop_hourly.csv)")
    args = ap.parse_args()

    stations_filter = [s.strip() for s in args.station.split(",") if s.strip()] if args.station else None

    try:
        logger.info(f"IMGW fetch — stations_filter={stations_filter or stations} output={args.out}")
        j = fetch_imgw()
        df = pd.DataFrame(j)
        norm = normalize(df, stations_filter=stations_filter)

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        append_aligned(norm, out)
        logger.info(f"Dopisałem {len(norm)} wierszy do {out}")
    except Exception as e:
        logger.exception(f"Błąd IMGW: {e}")
        raise

if __name__ == "__main__":
    main()
