# -*- coding: utf-8 -*-
"""
Fetcher GIOS dla Słupska — zapisuje bieżące godziny pomiarów (PM10, PM2.5, NO2, O3).
Wyjście: data/gios_slupsk.csv (timestamp, station, PM2.5, PM10, NO2, O3)

Od refaktoryzacji licencyjnej (2026-09) GIOŚ jest GŁÓWNYM źródłem pomiarów
zanieczyszczeń w pipeline (zamiast WAQI) — dane publiczne, komercyjnie
reużywalne pod warunkiem podania źródła. Pełną historię buduje/uzupełnia
gios_real_backfill.py; ten skrypt dopisuje tylko bieżącą godzinę (uruchamiany
cyklicznie, np. co godzinę z run_hourly.bat).
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
import pandas as pd

API_BASE = "https://api.gios.gov.pl/pjp-api/v1/rest"
OUT = Path(__file__).resolve().parents[1] / "data" / "gios_slupsk.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)

# Coordinates for Słupsk (approx)
SLUPSK_LAT = 54.4639
SLUPSK_LON = 17.0287
TARGET_CODES = {"PM10", "PM2.5", "NO2", "O3"}


def _safe_json(r):
    r.raise_for_status()
    return r.json()


def _nearest_station():
    # use /station/findAll (returns paginated Polish JSON with key 'Lista stacji pomiarowych')
    url = f"{API_BASE}/station/findAll"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        j = resp.json()
    except Exception as e:
        print(f"[DBG] GIOS metadata fetch failed: {e}")
        return None

    stations = []
    # handle both direct list and paginated dict formats
    if isinstance(j, list):
        stations = j
    elif isinstance(j, dict):
        # common Polish key from API: 'Lista stacji pomiarowych'
        member_key = next((k for k in j.keys() if isinstance(j[k], list)), None)
        if member_key and isinstance(j.get(member_key), list):
            stations.extend(j.get(member_key) or [])
            # handle pagination if present
            total_pages = int(j.get('totalPages') or 1)
            if total_pages > 1:
                for p in range(1, total_pages):
                    try:
                        page_j = requests.get(f"{url}?page={p}", timeout=20).json()
                        stations.extend(page_j.get(member_key) or [])
                    except Exception:
                        break
        else:
            # fallback: find first list value
            for v in j.values():
                if isinstance(v, list):
                    stations = v
                    break
    if not stations:
        print(f"[DBG] GIOS metadata: no stations list found in response; keys={list(j.keys()) if isinstance(j, dict) else 'n/a'}")
        return None

    def _get_station_name(st):
        return st.get('stationName') or st.get('Nazwa stacji') or st.get('Kod stacji') or st.get('Nazwa miasta')

    def _get_lat_lon(st):
        # support English/Polish keys and common alternatives
        lat_keys = ['gegrLat', 'WGS84 \u03c6 N', 'WGS84 φ N', 'latitude', 'lat']
        lon_keys = ['gegrLon', 'WGS84 \u03bb E', 'WGS84 \u03bb E', 'WGS84 λ E', 'longitude', 'lon']
        lat = None
        lon = None
        for k in lat_keys:
            if k in st and st.get(k) not in (None, ''):
                try:
                    lat = float(str(st.get(k)).replace(',', '.'))
                    break
                except Exception:
                    continue
        for k in lon_keys:
            if k in st and st.get(k) not in (None, ''):
                try:
                    lon = float(str(st.get(k)).replace(',', '.'))
                    break
                except Exception:
                    continue
        return lat, lon

    sample_names = [_get_station_name(s) for s in stations[:5]]
    print(f"[DBG] GIOS metadata: returned {len(stations)} stations; sample names: {sample_names}")

    # pick nearest by available lat/lon keys AND station must expose numeric id for /station/sensors
    best = None
    best_d = 1e9
    for s in stations:
        lat, lon = _get_lat_lon(s)
        if lat is None or lon is None:
            continue
        # prefer stations that have numeric identifier usable by /station/sensors
        station_ident = s.get('id') or s.get('Identyfikator stacji')
        if station_ident in (None, ''):
            # skip stations that only have a textual code
            continue
        d = (lat - SLUPSK_LAT) ** 2 + (lon - SLUPSK_LON) ** 2
        if d < best_d:
            best_d = d
            best = s

    if best is None:
        print("[DBG] No station with valid lat/lon found in GIOS response (checked gegrLat / WGS84 keys)")
    else:
        name = _get_station_name(best)
        # id may be under 'id' or 'Identyfikator stacji'
        station_id = best.get('id') or best.get('Identyfikator stacji') or best.get('Kod stacji')
        lat, lon = _get_lat_lon(best)
        print(f"[DBG] Nearest station: {name} (id={station_id}, lat={lat}, lon={lon})")
    return best


def _sensors_for_station(station_id):
    url = f"{API_BASE}/station/sensors/{station_id}"
    j = _safe_json(requests.get(url, timeout=10))
    # normalize various JSON-LD shapes into a list of sensor dicts with keys: id and param.paramCode
    if isinstance(j, list):
        sensors = j
    elif isinstance(j, dict):
        # find first list present (API uses Polish keys like 'Lista stanowisk pomiarowych dla podanej stacji')
        sensors = next((v for v in j.values() if isinstance(v, list)), [])
    else:
        sensors = []

    normalized = []
    for s in sensors:
        norm = {}
        # sensor id may be under 'Identyfikator stanowiska' or 'id'
        norm['id'] = s.get('Identyfikator stanowiska') or s.get('id') or s.get('Id stanowiska')
        # parameter code may be under Polish keys
        param_code = s.get('Wska\u017anik - kod') or s.get('Wska\u017anik - wz\u00f3r') or s.get('Wska\u017anik') or (s.get('param') or {}).get('paramCode')
        norm['param'] = {'paramCode': param_code} if param_code else (s.get('param') or {})
        normalized.append(norm)
    return normalized


def _fetch_sensor_data(sensor_id):
    url = f"{API_BASE}/data/getData/{sensor_id}"
    j = _safe_json(requests.get(url, timeout=10))
    # normalize to {'values': [{'date':..., 'value': ...}, ...]}
    values = []
    if isinstance(j, dict):
        # find first list of measurements (Polish key: 'Lista danych pomiarowych')
        data_list = next((v for v in j.values() if isinstance(v, list)), [])
    elif isinstance(j, list):
        data_list = j
    else:
        data_list = []

    for item in data_list:
        date = item.get('Data') or item.get('date') or item.get('Date')
        val = item.get('Warto\u015b\u0107') or item.get('value') or item.get('Value')
        values.append({'date': date, 'value': val})
    return {'values': values}

def _pick_values(sensors):
    # return dict: code -> latest numeric value (last full hour)
    out = {}
    for s in sensors:
        param = s.get("param") or {}
        code = (param.get("paramCode") or "").upper()
        sid = s.get("id")
        # debug which param codes we see
        if code:
            print(f"[DBG] sensor paramCode={code}, sensorId={sid}")
        if code not in TARGET_CODES:
            continue
        try:
            data = _fetch_sensor_data(sid)
            # data is dict with 'values' maybe under 'values'
            values = data.get("values") or []
            if not values:
                continue
            # find latest non-null value
            for v in values:
                val = v.get("value")
                if val is not None:
                    out[code] = val
                    print(f"[DBG] picked {code}={val} from sensor {sid}")
                    break
        except Exception as e:
            print(f"[DBG] error fetching sensor {sid}: {e}")
            continue
    return out


CANONICAL_COLUMNS = ["timestamp", "station", "PM2.5", "PM10", "NO2", "O3"]


def _last_saved_ts(path: Path):
    try:
        last = pd.read_csv(path, usecols=["timestamp"]).iloc[-1]["timestamp"]
        return pd.to_datetime(last)
    except Exception:
        return None


def main():
    try:
        st = _nearest_station()
        if not st:
            print("[WARN] Nie znalazlem stacji GIOS.")
            return
        # station id/name may be in English or Polish keys
        station_id = st.get("id") or st.get('Identyfikator stacji') or st.get('Kod stacji')
        station_name = st.get("stationName") or st.get('Nazwa stacji') or station_id
        sensors = _sensors_for_station(station_id)
        selected = [s for s in sensors if (s.get("param") or {}).get("paramCode")]
        vals = _pick_values(selected)

        # build row for current last-full-hour (Europe/Warsaw naive, spójnie z resztą pipeline'u)
        now = datetime.now(ZoneInfo("Europe/Warsaw")).replace(minute=0, second=0, microsecond=0, tzinfo=None)
        row = {"timestamp": now, "station": station_name}
        for k in TARGET_CODES:
            row[k] = vals.get(k)
        df_row = pd.DataFrame([row])

        if OUT.exists() and _last_saved_ts(OUT) == now:
            print(f"[INFO] Duplikat timestamp {now} — pomijam zapis.")
            return

        # Wyrównaj kolumny do nagłówka pliku (albo kolejności kanonicznej dla nowego pliku)
        # PRZED zapisem — inaczej dopisanie z inną kolejnością kolumn po cichu przestawia
        # wartości między kolumnami (patrz analogiczny komentarz w waqi_fetch.py).
        if OUT.exists():
            target_columns = pd.read_csv(OUT, nrows=0).columns.tolist()
        else:
            target_columns = CANONICAL_COLUMNS
        for col in target_columns:
            if col not in df_row.columns:
                df_row[col] = pd.NA
        df_row = df_row[target_columns]

        mode = "a" if OUT.exists() else "w"
        header = not OUT.exists()
        df_row.to_csv(OUT, mode=mode, header=header, index=False)
        print(f"[OK] Zapisano wiersz GIOS: {OUT}")
    except Exception as e:
        print(f"[ERR] GIOS fetch error: {e}")


if __name__ == '__main__':
    main()
