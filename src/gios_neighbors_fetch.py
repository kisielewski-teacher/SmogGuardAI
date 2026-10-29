# -*- coding: utf-8 -*-
"""
gios_neighbors_fetch.py — historia PM10 z sasiednich stacji GIOS (do cech "co dzieje sie wokol Slupska").

Smog jest czesto NIESIONY wiatrem z innych miejsc, wiec PM10 ze stacji w odleglosci 60-100 km
(Koszalin, Koscierzyna, Gdynia...) moze "zapowiadac" to, co za kilka godzin dotrze do Slupska.
Skrypt pobiera godzinowe PM10 z archiwum GIOS (to samo API co gios_real_backfill.py) i zapisuje
jedna tabele: data/neighbors_pm10.csv (timestamp + po jednej kolumnie na stacje).

Uzycie:
    py src/gios_neighbors_fetch.py [--start 2022-01-01]
Istniejace dane sa DOLACZANE (nic nie jest kasowane), brakujace godziny pozostaja puste.
"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gios_real_backfill import fetch_sensor_history  # noqa: E402

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data" / "neighbors_pm10.csv"
API = "https://api.gios.gov.pl/pjp-api/v1/rest"

# id stacji GIOS -> krotka nazwa kolumny; odleglosc od Slupska w nawiasie (km)
NEIGHBORS = {
    966: "koszalin",        # Koszalin, Al. Armii Krajowej (63 km, zachod)
    10934: "kolobrzeg",     # Kolobrzeg, ul. Zolkiewskiego (98 km, zachod-poludniowy zachod)
    981: "szczecinek",      # Szczecinek, ul. 1 Maja (86 km, poludniowy zachod)
    16157: "polczyn",       # Polczyn-Zdroj (100 km, poludnie)
    740: "koscierzyna",     # Koscierzyna (72 km, poludniowy wschod)
    16397: "wejherowo",     # Wejherowo (79 km, wschod)
    732: "gdynia",          # Gdynia, ul. Porebskiego (95 km, wschod)
    736: "gdansk",          # Gdansk, ul. Leczkowa (103 km, wschod)
}


def pm10_sensor_id(station_id: int):
    r = requests.get(f"{API}/station/sensors/{station_id}", params={"size": 100}, timeout=30)
    r.raise_for_status()
    j = r.json()
    items = next((v for v in j.values() if isinstance(v, list)), [])
    for s in items:
        if str(s.get("Wskaźnik - kod", "")).upper() == "PM10":
            return s["Identyfikator stanowiska"]
    return None


def with_retries(fn, *args, attempts: int = 4, wait: float = 5.0):
    """API GIOS bywa wolne: ponawiamy z rosnaca przerwa zamiast przerywac cala prace."""
    last = None
    for i in range(attempts):
        try:
            return fn(*args)
        except (requests.RequestException, RuntimeError) as e:
            last = e
            print(f"    [retry {i + 1}/{attempts}] {type(e).__name__}: {str(e)[:80]}")
            time.sleep(wait * (i + 1))
    raise last


def save(new: pd.DataFrame) -> None:
    if OUT.exists():
        old = pd.read_csv(OUT, parse_dates=["timestamp"]).set_index("timestamp")
        new = new.combine_first(old).sort_index()   # nowe wartosci maja pierwszenstwo, stare uzupelniaja luki i inne kolumny
    new.to_csv(OUT, date_format="%Y-%m-%d %H:%M:%S")


def main():
    ap = argparse.ArgumentParser(description="PM10 z sasiednich stacji GIOS")
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--pause", type=float, default=0.3, help="przerwa miedzy stacjami [s] (grzecznosc wobec API)")
    args = ap.parse_args()

    start = pd.Timestamp(args.start)
    now = pd.Timestamp.now().floor("h")
    grid = pd.date_range(start.floor("h"), now, freq="h")
    ok = 0
    for sid, name in NEIGHBORS.items():
        try:
            sensor = with_retries(pm10_sensor_id, sid)
            if sensor is None:
                print(f"[WARN] {name}: brak czujnika PM10 — pomijam")
                continue
            hist = with_retries(fetch_sensor_history, sensor, start, now)
        except Exception as e:  # noqa: BLE001 - jedna wadliwa stacja nie moze zatrzymac reszty
            print(f"[WARN] {name}: pominieta po bledach ({type(e).__name__})")
            continue
        if hist.empty:
            print(f"[WARN] {name}: brak danych w archiwum")
            continue
        s = hist.set_index("timestamp")["value"].groupby(level=0).mean()
        frame = pd.DataFrame({name: s}).reindex(grid)
        frame.index.name = "timestamp"
        save(frame)                      # zapis po kazdej stacji — postep nie ginie przy bledzie
        ok += 1
        print(f"[OK] {name}: {len(s)} godzin ({s.index.min():%Y-%m-%d} .. {s.index.max():%Y-%m-%d})")
        time.sleep(args.pause)

    if not ok:
        print("[ERR] Nie pobrano zadnych danych.")
        sys.exit(1)
    print(f"[OK] Gotowe: {ok}/{len(NEIGHBORS)} stacji -> {OUT}")


if __name__ == "__main__":
    main()
