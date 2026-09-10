# -*- coding: utf-8 -*-
"""
Fetch danych z Airly dla Słupska (jeśli masz AIRLY_KEY w .env / w zmiennych środowiskowych).
Wyjście: data/airly_slupsk.csv (timestamp, PM2.5, PM10, temperature, humidity, pressure, station)
"""
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import pandas as pd
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data" / "airly_slupsk.csv"

load_dotenv(BASE / ".env")
API_KEY = os.getenv("AIRLY_KEY")
LAT = float(os.getenv("LAT", "54.4639"))
LON = float(os.getenv("LON", "17.0287"))

# Airly endpoints
NEAREST_URL = "https://airapi.airly.eu/v2/installations/nearest"


def _get_nearest_installation():
    if not API_KEY:
        raise RuntimeError("Brak AIRLY_KEY w .env lub w zmiennych środowiskowych")
    headers = {"apikey": API_KEY}
    params = {"lat": LAT, "lng": LON, "maxDistanceKM": 10, "maxResults": 1}
    r = requests.get(NEAREST_URL, headers=headers, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise RuntimeError("Brak instalacji Airly w pobliżu")
    return data[0]


def parse_installation(inst):
    # installation has 'id' and may include 'current' -> 'values'
    try:
        inst_id = inst.get("id")
        inst_name = inst.get("address", {}).get("street", inst.get("address", {}).get("displayAddress", "Airly"))
    except Exception:
        inst_id = None
        inst_name = "Airly"
    return inst_id, inst_name


def fetch_measurements(installation):
    # get installation measurements
    headers = {"apikey": API_KEY}
    url = f"https://airapi.airly.eu/v2/measurements/installation?installationId={installation}"
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def main():
    try:
        if not API_KEY:
            print("[WARN] AIRLY_KEY not set — skipping Airly fetch")
            return
        inst = _get_nearest_installation()
        inst_id, inst_name = parse_installation(inst)
        data = fetch_measurements(inst_id)
        # data contains 'current' -> 'values'
        current = data.get("current", {})
        values = {v.get("name"): v.get("value") for v in current.get("values", [])}

        row = {
            "timestamp": datetime.now(ZoneInfo("Europe/Warsaw")).replace(minute=0, second=0, microsecond=0, tzinfo=None),
            "station": inst_name,
            "PM2.5": values.get("PM25") if values.get("PM25") is not None else values.get("PM2.5"),
            "PM10": values.get("PM10"),
            "temperature": values.get("TEMPERATURE"),
            "humidity": values.get("HUMIDITY"),
            "pressure": values.get("PRESSURE"),
        }
        df = pd.DataFrame([row])
        if OUT.exists():
            df.to_csv(OUT, mode="a", header=False, index=False)
        else:
            df.to_csv(OUT, index=False)
        print(f"[OK] Zapisano Airly -> {OUT}")
    except Exception as e:
        print(f"[ERR] airly_fetch: {e}")


if __name__ == '__main__':
    main()
