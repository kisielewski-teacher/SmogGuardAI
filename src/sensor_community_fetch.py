# -*- coding: utf-8 -*-
"""
Fetch z sensor.community (AirRohr) w okolicy Słupska.
Wyjście: data/sensor_community_slupsk.csv (timestamp, PM2.5, PM10, sensor_id)
"""
import requests
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import os

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data" / "sensor_community_slupsk.csv"
LAT = float(os.getenv("LAT", "54.4639"))
LON = float(os.getenv("LON", "17.0287"))
RADIUS_KM = float(os.getenv("SENSOR_COMMUNITY_RADIUS_KM", "25"))

API = "https://data.sensor.community/airrohr/v1/filter/area"


def _query_radius(radius_km: int):
    params = {"lat": LAT, "lon": LON, "dist": int(radius_km * 1000)}
    r = requests.get(API, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def main():
    try:
        # try expanding radii until we find a sensor with PM2.5
        radii = [5, 10, 25, 50, 100]
        found = None
        for r_km in radii:
            try:
                arr = _query_radius(r_km)
            except Exception:
                arr = []
            if arr:
                # search for PM2.5 among returned sensors
                for s in arr:
                    last = s.get('sensordatavalues') or []
                    pm25 = None
                    pm10 = None
                    ts = None
                    for v in reversed(last):
                        if v.get('value') is None:
                            continue
                        vt = v.get('value_type', '')
                        if vt.upper() in ('P2', 'PM25', 'PM2.5') and pm25 is None:
                            try:
                                pm25 = float(v.get('value'))
                            except Exception:
                                pm25 = None
                        if vt.upper() in ('P1', 'PM10') and pm10 is None:
                            try:
                                pm10 = float(v.get('value'))
                            except Exception:
                                pm10 = None
                    if pm25 is not None:
                        # sensor provides PM2.5 — select it
                        try:
                            ts_str = s.get('lastMeasurement', {}).get('dateTime') or s.get('lastMeasurement')
                            from dateutil import parser
                            ts = parser.parse(ts_str) if ts_str else None
                        except Exception:
                            ts = None
                        found = {'sensor': s, 'pm25': pm25, 'pm10': pm10, 'timestamp': ts, 'radius_km': r_km}
                        break
            if found:
                print(f"[INFO] Found sensor within {r_km} km")
                break
        if not found:
            print('[WARN] sensor_community_fetch: brak czujników z PM2.5 w promieniu do 100 km')
            return

        best = found
        row = {
            'timestamp': (best['timestamp'].astimezone().replace(minute=0, second=0, microsecond=0) if best['timestamp'] is not None else datetime.now(ZoneInfo("Europe/Warsaw")).replace(minute=0, second=0, microsecond=0, tzinfo=None)),
            'sensor_id': (best['sensor'].get('sensor', {}).get('id') if isinstance(best['sensor'].get('sensor'), dict) else best['sensor'].get('id')),
            'PM2.5': best['pm25'],
            'PM10': best['pm10']
        }
        df = pd.DataFrame([row])
        if OUT.exists():
            df.to_csv(OUT, mode='a', header=False, index=False)
        else:
            df.to_csv(OUT, index=False)
        print(f"[OK] Zapisano Sensor.Community -> {OUT} (radius_km={best['radius_km']})")
    except Exception as e:
        print(f"[ERR] sensor_community_fetch: {e}")


if __name__ == '__main__':
    main()
