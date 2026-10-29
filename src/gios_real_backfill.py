# -*- coding: utf-8 -*-
"""
gios_real_backfill.py — buduje/uzupełnia CAŁĄ historię PM10, PM2.5, NO2, O3
prawdziwymi, zweryfikowanymi pomiarami z oficjalnego API GIOS
(archivalData/getDataBySensor), niezależnie od WAQI.

GIOŚ jest od refaktoryzacji licencyjnej (2026-09) GŁÓWNYM źródłem pomiarów
zanieczyszczeń w pipeline — plik wynikowy (data/gios_slupsk.csv) jest
samodzielną, ciągłą siatką godzinową i nie zależy już od aqicn_slupsk_data.csv
(WAQI). Dane GIOŚ są danymi publicznymi (do zweryfikowania na
https://powietrze.gios.gov.pl), co pozwala na komercyjne wykorzystanie pod
warunkiem podania źródła — patrz ToDo.md.

Stacja: Słupsk, ul. Kniaziewicza (najbliższa stacja GIOŚ, wykrywana
automatycznie na podstawie współrzędnych — zob. _nearest_station()
w gios_fetch.py).

Uruchomienie (jednorazowo lub okresowo, żeby domknąć ewentualne luki):
    py src/gios_real_backfill.py [--start YYYY-MM-DD]
"""
from pathlib import Path
from datetime import timedelta
import argparse
import sys
import time

import pandas as pd
import requests

from gios_fetch import _nearest_station, _sensors_for_station, TARGET_CODES

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
DATA.mkdir(parents=True, exist_ok=True)
GIOS_PATH = DATA / "gios_slupsk.csv"

API_BASE = "https://api.gios.gov.pl/pjp-api/v1/rest"
CHUNK_DAYS = 20  # bezpieczny rozmiar (limit GIOS: 366 dni/zapytanie, size max 500/strona)

CANONICAL_COLUMNS = ["timestamp", "station", "PM2.5", "PM10", "NO2", "O3"]

# Kod parametru GIOS (paramCode) -> nazwa kolumny w gios_slupsk.csv
CODE_TO_COLUMN = {"PM10": "PM10", "PM2.5": "PM2.5", "NO2": "NO2", "O3": "O3"}


def _discover_sensor_ids() -> tuple[str, dict[str, int]]:
    """Znajduje najbliższą stację GIOS i zwraca (nazwa_stacji, {paramCode: sensor_id})."""
    st = _nearest_station()
    if not st:
        raise RuntimeError("Nie udało się znaleźć najbliższej stacji GIOŚ.")
    station_id = st.get("id") or st.get("Identyfikator stacji") or st.get("Kod stacji")
    station_name = st.get("stationName") or st.get("Nazwa stacji") or str(station_id)
    sensors = _sensors_for_station(station_id)
    sensor_ids: dict[str, int] = {}
    for s in sensors:
        code = ((s.get("param") or {}).get("paramCode") or "").upper()
        sid = s.get("id")
        if code in TARGET_CODES and sid:
            sensor_ids[code] = sid
    missing = TARGET_CODES - set(sensor_ids)
    if missing:
        print(f"[WARN] Stacja {station_name} nie ma czujników dla: {sorted(missing)} — "
              f"te kolumny pozostaną puste.")
    return station_name, sensor_ids


def fetch_sensor_history(sensor_id: int, date_from: pd.Timestamp, date_to: pd.Timestamp) -> pd.DataFrame:
    """Pobiera pełną historię godzinową jednego czujnika GIOS (z paginacją po CHUNK_DAYS dni)."""
    rows = []
    cur = date_from
    while cur < date_to:
        chunk_end = min(cur + timedelta(days=CHUNK_DAYS), date_to)
        page = 0
        while True:
            params = {
                "dateFrom": cur.strftime("%Y-%m-%d %H:%M"),
                "dateTo": chunk_end.strftime("%Y-%m-%d %H:%M"),
                "size": 500,
                "page": page,
            }
            url = f"{API_BASE}/archivalData/getDataBySensor/{sensor_id}"
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            j = r.json()
            lst_key = next((k for k in j.keys() if isinstance(j.get(k), list)), None)
            items = (j.get(lst_key) or []) if lst_key else []
            if not items:
                break
            for it in items:
                rows.append({"timestamp": it.get("Data"), "value": it.get("Wartość")})
            total_pages = int(j.get("totalPages") or 1)
            page += 1
            if page >= total_pages:
                break
        cur = chunk_end
        time.sleep(0.3)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")


def main():
    ap = argparse.ArgumentParser(description="Pełny historyczny backfill PM10/PM2.5/NO2/O3 z GIOŚ.")
    ap.add_argument("--start", default=None, help="Data początkowa YYYY-MM-DD (domyślnie: najstarsza dostępna w gios_slupsk.csv, "
                                                    "albo 30 dni wstecz jeśli plik nie istnieje).")
    args = ap.parse_args()

    now = pd.Timestamp.now().floor("h")

    if args.start:
        data_start = pd.Timestamp(args.start)
    elif GIOS_PATH.exists():
        existing = pd.read_csv(GIOS_PATH, usecols=["timestamp"], parse_dates=["timestamp"])
        data_start = existing["timestamp"].min() if not existing.empty else now - timedelta(days=30)
    else:
        data_start = now - timedelta(days=30)

    print(f"Zakres docelowy: {data_start} -> {now}")

    station_name, sensor_ids = _discover_sensor_ids()
    if not sensor_ids:
        print("[ERR] Brak jakichkolwiek czujników GIOŚ dla tej stacji — przerywam.")
        sys.exit(1)

    series: dict[str, pd.Series] = {}
    for code, sid in sensor_ids.items():
        print(f"[GIOS] Pobieram historię {code} (sensor {sid})...")
        hist = fetch_sensor_history(sid, data_start, now)
        print(f"       -> {len(hist)} realnych pomiarów {code}")
        if not hist.empty:
            series[CODE_TO_COLUMN[code]] = hist.set_index("timestamp")["value"]

    if not series:
        print("[ERR] Nie udało się pobrać żadnych danych z GIOŚ — przerywam.")
        sys.exit(1)

    full_hours = pd.date_range(data_start.floor("h"), now, freq="h")
    out = pd.DataFrame(index=full_hours)
    out.index.name = "timestamp"
    for col, s in series.items():
        out[col] = s.reindex(full_hours)
    out = out.reset_index()
    out.insert(1, "station", station_name)
    for col in CANONICAL_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[CANONICAL_COLUMNS]

    # Nie kasuj historii sprzed --start: dolacz istniejace wiersze, a nowe pomiary
    # (niepuste) maja pierwszenstwo przed starymi w nakladajacym sie zakresie.
    if GIOS_PATH.exists():
        old = pd.read_csv(GIOS_PATH, parse_dates=["timestamp"])
        if not old.empty:
            merged = pd.concat([old, out]).sort_values("timestamp")
            value_cols = [c for c in CANONICAL_COLUMNS if c not in ("timestamp", "station")]
            out = (merged.groupby("timestamp", as_index=False)
                   .agg({"station": "last", **{c: "last" for c in value_cols}})
                   [CANONICAL_COLUMNS])

    out.to_csv(GIOS_PATH, index=False)
    counts = {c: int(out[c].notna().sum()) for c in ["PM10", "PM2.5", "NO2", "O3"]}
    print(f"Zapisano {len(out)} wierszy do {GIOS_PATH} (pomiary: {counts})")


if __name__ == "__main__":
    main()
