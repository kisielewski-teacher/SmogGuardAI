# -*- coding: utf-8 -*-
"""gios_backfill.py - uzupelnia luke w data/gios_slupsk.csv z archiwalnego API GIOS (PM10, godzinowo).

Uzycie: py src/gios_backfill.py [--from 2026-10-30]   (domyslnie od ostatniego zapisanego dnia)
Wiersze GIOS maja pierwszenstwo przed wpisami z tego samego okresu zrobionymi przez gios_fetch.py.
"""
from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data" / "gios_slupsk.csv"
API = "https://api.gios.gov.pl/pjp-api/v1/rest/archivalData/getDataBySensor/{sid}"
SENSOR_PM10 = 16071  # Slupsk, ul. Kniaziewicza, PM10 1h
STATION = "Słupsk, ul. Kniaziewicza"


def fetch_pm10(date_from: str, date_to: str, sensor: int = SENSOR_PM10) -> pd.DataFrame:
    rows, page = [], 0
    while True:
        r = requests.get(API.format(sid=sensor), timeout=30, params={
            "dateFrom": f"{date_from} 00:00", "dateTo": f"{date_to} 23:59", "size": 500, "page": page})
        r.raise_for_status()
        j = r.json()
        rows += next((v for v in j.values() if isinstance(v, list)), [])
        if page + 1 >= int(j.get("totalPages", 1)):
            break
        page += 1
    df = pd.DataFrame({"timestamp": [x.get("Data") for x in rows],
                       "PM10": [x.get("Wartość") for x in rows]})
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["PM10"] = pd.to_numeric(df["PM10"], errors="coerce")
    return df.dropna(subset=["timestamp", "PM10"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=None)
    a = ap.parse_args()
    old = pd.read_csv(OUT, parse_dates=["timestamp"])
    start = a.start or (old["timestamp"].max().normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    new = fetch_pm10(start, datetime.now().strftime("%Y-%m-%d"))
    if new.empty:
        print("[WARN] Archiwum GIOS nie zwrocilo danych."); return 1
    new["station"] = STATION
    cut = pd.Timestamp(start)
    keep = old[old["timestamp"] < cut]
    out = pd.concat([keep, new], ignore_index=True).drop_duplicates("timestamp", keep="last")
    out = out.sort_values("timestamp")[["timestamp", "station", "PM2.5", "PM10", "NO2", "O3"]]
    out.to_csv(OUT, index=False, date_format="%Y-%m-%d %H:%M:%S")
    print(f"[OK] {len(new)} godzin PM10 ({new.timestamp.min()} .. {new.timestamp.max()}); plik: {len(out)} wierszy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
