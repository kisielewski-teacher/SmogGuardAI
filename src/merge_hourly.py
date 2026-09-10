# -*- coding: utf-8 -*-
"""
merge_hourly.py — odporna wersja scalania danych WAQI + IMGW

Funkcje:
- Wczytanie CSV z wykryciem separatora ("," lub ";").
- Odporność na ParserError: engine="python" + on_bad_lines="skip" (loguje liczbę pominiętych linii).
- Ujednolicenie kolumny czasu: parsowanie i zrzucenie strefy (naive datetime64[ns]).
- Sortowanie, drop NaT, merge_asof z tolerancją 1h.
- Logi do logs/merge_YYYYMMDD.log + konsola.

Uruchomienie:
py src\\merge_hourly.py
"""
from pathlib import Path
import logging
from datetime import datetime
import pandas as pd

# --- Ścieżki ---
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

waqi_path = DATA_DIR / "aqicn_slupsk_data.csv"
imgw_path = DATA_DIR / "imgw_synop_hourly.csv"
gios_path = DATA_DIR / "gios_slupsk.csv"
out_path  = DATA_DIR / "merged_hourly.csv"

# --- Logowanie ---
log_path = LOGS_DIR / f"merge_{datetime.now():%Y%m%d}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("merge")

# --- Pomocnicze ---
def _detect_sep(path: Path) -> str:
    """Proste wykrycie separatora: ";" jeśli w nagłówku jest średnik, inaczej ","."""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            header = f.readline()
        if ";" in header and "," not in header:
            return ";"
        return ","
    except Exception:
        return ","  # bezpieczny domyślny


def _read_csv_robust(path: Path) -> pd.DataFrame:
    """Wczytaj CSV z odpornością na błędne wiersze."""
    if not path.exists():
        logger.warning(f"Brak pliku: {path}")
        return pd.DataFrame()
    sep = _detect_sep(path)
    try:
        df = pd.read_csv(path, sep=sep)
        bad_lines = 0
    except pd.errors.ParserError as e:
        logger.warning(f"ParserError dla {path}: {e}. Wczytuję z engine='python' i pomijam złe linie.")
        df = pd.read_csv(path, sep=sep, engine="python", on_bad_lines="skip")
        bad_lines = None  # nie znamy dokładnej liczby; odnotuj poniżej
    # Parsuj timestamp — obsłuż mieszane strefy czasowe (np. "+01:00" i naive)
    if "timestamp" in df.columns:
        def _parse_ts(s):
            if pd.isna(s):
                return pd.NaT
            try:
                t = pd.Timestamp(s)
                if t.tzinfo is not None:
                    return t.tz_convert("Europe/Warsaw").tz_localize(None)
                return t
            except Exception:
                return pd.NaT
        df["timestamp"] = df["timestamp"].apply(_parse_ts)
    # Informacja o liczbie wierszy
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            total_lines = sum(1 for _ in f) - 1  # bez nagłówka
    except Exception:
        total_lines = None
    msg = f"Wczytano {len(df)} wierszy z {path} (sep='{sep}'"
    if bad_lines is None:
        msg += f", łącznie w pliku ~{total_lines}, pominięte złe linie)"
    else:
        msg += ")"
    logger.info(msg)
    return df


def _normalize_time_tz(df: pd.DataFrame) -> pd.DataFrame:
    """Ujednolić typ czasu: jeśli tz-aware, konwertuj do Europe/Warsaw i zrzuc strefę (naive)."""
    if "timestamp" not in df.columns or df.empty:
        return df
    dtype_str = str(df["timestamp"].dtype)
    if dtype_str.startswith("datetime64[ns,"):
        df["timestamp"] = df["timestamp"].dt.tz_convert("Europe/Warsaw").dt.tz_localize(None)
    return df


# --- Główna logika ---
def main():
    w = _read_csv_robust(waqi_path)
    i = _read_csv_robust(imgw_path)

    if w.empty:
        logger.warning("Brak danych WAQI — zatrzymuję scalanie.")
        return
    if i.empty:
        logger.warning("Brak danych IMGW — zapisuję tylko WAQI.")
        w.to_csv(out_path, index=False)
        return

    # Czyszczenie NaT i sortowanie
    before_w, before_i = len(w), len(i)
    w = w.dropna(subset=["timestamp"]).sort_values("timestamp")
    i = i.dropna(subset=["timestamp"]).sort_values("timestamp")
    logger.info(f"Drop NaT: WAQI {before_w - len(w)} usuniętych, IMGW {before_i - len(i)} usuniętych")

    # Ujednolicenie czasu
    w = _normalize_time_tz(w)
    i = _normalize_time_tz(i)

    if w.empty or i.empty:
        logger.warning("Po czyszczeniu brak danych do scalania — zapisuję WAQI.")
        w.to_csv(out_path, index=False)
        return

    # Scalanie asof z tolerancją 1h
    merged = pd.merge_asof(
        w, i,
        on="timestamp",
        direction="backward",
        tolerance=pd.Timedelta("1h")
    )

    # Jeśli mamy dane GIOS (PM2.5/PM10 itp.), dołącz je (nearest, tol=1h)
    if gios_path.exists():
        g = _read_csv_robust(gios_path)
        if not g.empty and "timestamp" in g.columns:
            g = g.dropna(subset=["timestamp"]).sort_values("timestamp")
            g = _normalize_time_tz(g)
            merged = pd.merge_asof(
                merged.sort_values("timestamp"),
                g.sort_values("timestamp"),
                on="timestamp", direction="nearest", tolerance=pd.Timedelta("1h")
            )

    # Dołącz dane Airly (jeśli istnieją)
    airly_path = DATA_DIR / 'airly_slupsk.csv'
    if airly_path.exists():
        a = _read_csv_robust(airly_path)
        if not a.empty and 'timestamp' in a.columns:
            a = a.dropna(subset=['timestamp']).sort_values('timestamp')
            a = _normalize_time_tz(a)
            merged = pd.merge_asof(
                merged.sort_values('timestamp'),
                a.sort_values('timestamp'),
                on='timestamp', direction='nearest', tolerance=pd.Timedelta('1h')
            )

    # Dołącz dane Sensor.Community (jeśli istnieją)
    sc_path = DATA_DIR / 'sensor_community_slupsk.csv'
    if sc_path.exists():
        s = _read_csv_robust(sc_path)
        if not s.empty and 'timestamp' in s.columns:
            s = s.dropna(subset=['timestamp']).sort_values('timestamp')
            s = _normalize_time_tz(s)
            merged = pd.merge_asof(
                merged.sort_values('timestamp'),
                s.sort_values('timestamp'),
                on='timestamp', direction='nearest', tolerance=pd.Timedelta('1h')
            )

    # --- Dołącz agregaty Syngeos (jeśli istnieją) ---
    syngeos_agg_path = DATA_DIR / 'syngeos_agg.csv'
    if syngeos_agg_path.exists():
        sg = _read_csv_robust(syngeos_agg_path)
        if not sg.empty and 'timestamp' in sg.columns:
            sg['timestamp'] = pd.to_datetime(sg['timestamp'], errors='coerce')
            sg = sg.dropna(subset=['timestamp']).sort_values('timestamp')
            # Kolumny oczekiwane: pm25_mean / pm10_mean (może też być pm25_median, pm25_count)
            rename_map = {}
            for c in ['pm25_mean', 'pm10_mean', 'pm25_median', 'pm10_median', 'pm25_count', 'pm10_count']:
                if c in sg.columns:
                    rename_map[c] = c
            if rename_map:
                sg = sg.rename(columns=rename_map)
            # scal przez nearest (tolerancja 1h)
            merged = pd.merge_asof(
                merged.sort_values('timestamp'),
                sg.sort_values('timestamp'),
                on='timestamp', direction='nearest', tolerance=pd.Timedelta('1h')
            )
            # sanity check: wartości PM w rozsądnym zakresie
            for col in ['pm25_mean', 'pm10_mean']:
                if col in merged.columns:
                    merged[col] = pd.to_numeric(merged[col], errors='coerce')
                    merged.loc[~merged[col].between(0, 500), col] = pd.NA
            # jeżeli brak canonicalnych kolumn PM w merged, uzupełnij z syngeos
            if 'PM2.5' not in merged.columns:
                merged['PM2.5'] = merged.get('pm25_mean')
            else:
                merged['PM2.5'] = merged['PM2.5'].fillna(merged.get('pm25_mean'))
            if 'PM10' not in merged.columns:
                merged['PM10'] = merged.get('pm10_mean')
            else:
                merged['PM10'] = merged['PM10'].fillna(merged.get('pm10_mean'))
            logger.info(f"Dołączono Syngeos (syngeos_agg.csv): wypełniono PM2.5/PM10 tam, gdzie brakowało pomiarów")

    merged.to_csv(out_path, index=False)
    logger.info(f"Zapisano {len(merged)} wierszy do {out_path}")


if __name__ == "__main__":
    main()
