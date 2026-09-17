# -*- coding: utf-8 -*-
"""
gios_real_backfill.py — uzupełnia CAŁĄ historię PM10 prawdziwymi, zweryfikowanymi
pomiarami z oficjalnego API GIOS (archivalData/getDataBySensor), zamiast danych
syntetycznych/fikcyjnych.

Zastępuje:
  - wiersze wcześniej wygenerowane sztucznie przez backfill_pm10_gap.py
    (2026-03-18 – 2026-04-20, oznaczone _backfilled=True, wartości losowe)
  - brakujące godziny (np. 2026-01-01 – 2026-02-23, oraz każdą lukę od
    ostatniego prawdziwego pomiaru WAQI aż do "teraz")

Źródło: https://api.gios.gov.pl/pjp-api/v1/rest/archivalData/getDataBySensor/{id}
Stacja: Słupsk, ul. Kniaziewicza (id stacji=725, id stanowiska PM10=16071)
Dane te są oficjalnymi, publicznymi pomiarami GIOŚ — możliwymi do zweryfikowania
na https://powietrze.gios.gov.pl.

Uruchomienie:
    py src/gios_real_backfill.py
"""
from pathlib import Path
from datetime import datetime, timedelta
import sys
import time

import pandas as pd
import requests

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
WAQI_PATH = DATA / "aqicn_slupsk_data.csv"
GIOS_PATH = DATA / "gios_slupsk.csv"

API_BASE = "https://api.gios.gov.pl/pjp-api/v1/rest"
PM10_SENSOR_ID = 16071  # Słupsk, ul. Kniaziewicza — PM10
STATION_NAME = "Słupsk, ul. Kniaziewicza"

CHUNK_DAYS = 20  # bezpieczny rozmiar (GIOS limit 366 dni/zapytanie, size max 500/strona)


def fetch_gios_chunk(date_from: pd.Timestamp, date_to: pd.Timestamp) -> pd.DataFrame:
    """Pobiera realne godzinowe pomiary PM10 z GIOS dla podanego zakresu."""
    rows = []
    page = 0
    while True:
        params = {
            "dateFrom": date_from.strftime("%Y-%m-%d %H:%M"),
            "dateTo": date_to.strftime("%Y-%m-%d %H:%M"),
            "size": 500,
            "page": page,
        }
        url = f"{API_BASE}/archivalData/getDataBySensor/{PM10_SENSOR_ID}"
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        j = r.json()
        lst_key = next((k for k in j.keys() if isinstance(j.get(k), list)), None)
        items = j.get(lst_key) or [] if lst_key else []
        if not items:
            break
        for it in items:
            rows.append({"timestamp": it.get("Data"), "PM10": it.get("Wartość")})
        total_pages = int(j.get("totalPages") or 1)
        page += 1
        if page >= total_pages:
            break
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["PM10"] = pd.to_numeric(df["PM10"], errors="coerce")
    return df.dropna(subset=["PM10"]).drop_duplicates(subset=["timestamp"])


def fetch_gios_full(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Pobiera pełny zakres, dzieląc na kawałki po CHUNK_DAYS dni."""
    chunks = []
    cur = start
    while cur < end:
        chunk_end = min(cur + timedelta(days=CHUNK_DAYS), end)
        print(f"[GIOS] pobieram {cur} -> {chunk_end} ...")
        try:
            df = fetch_gios_chunk(cur, chunk_end)
            print(f"       -> {len(df)} realnych pomiarów PM10")
            chunks.append(df)
        except Exception as e:
            print(f"[WARN] blad pobierania {cur}-{chunk_end}: {e}")
        cur = chunk_end
        time.sleep(0.3)
    if not chunks:
        return pd.DataFrame(columns=["timestamp", "PM10"])
    out = pd.concat(chunks, ignore_index=True).drop_duplicates(subset=["timestamp"])
    return out.sort_values("timestamp").reset_index(drop=True)


def main():
    waqi = pd.read_csv(WAQI_PATH)
    waqi["timestamp"] = pd.to_datetime(waqi["timestamp"])
    waqi = waqi.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

    data_start = waqi["timestamp"].min().floor("h")
    now = pd.Timestamp.now().floor("h")
    print(f"Zakres docelowy: {data_start} -> {now}")

    gios = fetch_gios_full(data_start, now)
    if gios.empty:
        print("[ERR] Brak danych z GIOS — przerywam.")
        sys.exit(1)
    print(f"Łącznie pobrano {len(gios)} realnych, zweryfikowanych pomiarów PM10 z GIOS "
          f"({gios['timestamp'].min()} .. {gios['timestamp'].max()})")

    # Zapisz surowe dane GIOS do gios_slupsk.csv (źródło/dowód pochodzenia danych)
    gios_out = gios.copy()
    gios_out["station"] = STATION_NAME
    gios_out["PM2.5"] = pd.NA
    gios_out["NO2"] = pd.NA
    gios_out["O3"] = pd.NA
    gios_out = gios_out[["timestamp", "station", "PM2.5", "PM10", "NO2", "O3"]]
    gios_out.to_csv(GIOS_PATH, index=False)
    print(f"Zapisano {len(gios_out)} wierszy do {GIOS_PATH}")

    # --- Zbuduj pełny ciągły zakres godzinowy i uzupełnij PM10 realnymi danymi GIOS ---
    full_hours = pd.date_range(data_start, now, freq="h")
    target_index = pd.DatetimeIndex(waqi["timestamp"]).union(full_hours)
    waqi = (
        waqi.set_index("timestamp")
        .reindex(target_index)
        .rename_axis("timestamp")
        .reset_index()
    )
    waqi = waqi.sort_values("timestamp").reset_index(drop=True)

    if "_backfilled" not in waqi.columns:
        waqi["_backfilled"] = None

    gios_map = gios.set_index("timestamp")["PM10"]

    n_replaced_fake = 0
    n_filled_missing = 0
    for idx, row in waqi.iterrows():
        ts = row["timestamp"]
        is_fake_backfilled = bool(row.get("_backfilled") is True or row.get("_backfilled") == "True")
        is_missing_pm10 = pd.isna(row.get("PM10"))
        if ts in gios_map.index and (is_fake_backfilled or is_missing_pm10):
            waqi.at[idx, "PM10"] = gios_map.loc[ts]
            waqi.at[idx, "_backfilled"] = True  # oznacza: uzupełnione z oficjalnego archiwum GIOS (dane realne)
            if is_fake_backfilled:
                n_replaced_fake += 1
            else:
                n_filled_missing += 1

    print(f"Zastąpiono {n_replaced_fake} sztucznych (syntetycznych) wierszy realnymi danymi GIOS")
    print(f"Uzupełniono {n_filled_missing} brakujących godzin realnymi danymi GIOS")

    waqi.to_csv(WAQI_PATH, index=False)
    print(f"Zapisano {len(waqi)} wierszy do {WAQI_PATH}")


if __name__ == "__main__":
    main()
