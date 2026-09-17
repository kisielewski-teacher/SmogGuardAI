
# -*- coding: utf-8 -*-
r"""
merge_pm10_results.py — scala pomiar + prognozę + pogodę w jeden plik dla dashboardu.

Użycie (przykład):
py src\merge_pm10_results.py ^
  --backtest data\aqicn_slupsk_data.csv ^
  --prediction outputs\pm10_pred_latest.csv ^
  --weather data\aqicn_slupsk_data.csv ^
  --time-col timestamp ^
  --coalesce-hist ^
  --out outputs\pm10_all_latest.csv
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np

# --------- Aliasy kolumn (PL -> EN) ----------
ALIASES = {
    "timestamp": ["timestamp", "time", "date", "datetime", "DateTime"],
    "pm10": ["pm10", "PM10", "pm_10", "PM_10", "pm10_value"],
    "pm25": ["pm25", "PM25", "pm_25", "PM_25"],
    "temp": ["temp", "temperatura"],
    "rh": ["rh", "wilgotnosc_wzgledna", "wilgotnosc", "humidity"],
    "pressure": ["pressure", "cisnienie", "ciśnienie"],
    "wind": ["wind", "wind_speed", "predkosc_wiatru", "wiatr"],
}

# --------- Pomocnicze: wykrycie separatora, robust read ----------
def detect_sep(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            h = f.readline()
            # Jeśli jest ; i nie ma , → raczej ; (typowe dla PL)
            return ";" if (";" in h and "," not in h) else ","
    except Exception:
        return ","

def read_csv_robust(path: Path, sep: str | None = None, encoding: str = "utf-8") -> pd.DataFrame:
    """Czyta CSV odpornie: wykrywa separator, w razie problemów przełącza na engine='python' i pomija złe linie."""
    real_sep = sep or detect_sep(path)
    try:
        return pd.read_csv(path, sep=real_sep, encoding=encoding)
    except pd.errors.ParserError:
        return pd.read_csv(path, sep=real_sep, encoding=encoding, engine="python", on_bad_lines="skip")

def normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    ren = {}
    for tgt, aliases in ALIASES.items():
        for a in aliases:
            if a in df.columns and tgt not in df.columns:
                ren[a] = tgt
                break
    df = df.rename(columns=ren)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df

def to_numeric_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def unify_time(df: pd.DataFrame, time_col: str = "timestamp") -> pd.DataFrame:
    """Ujednolica datetime do naive (bez strefy), toleruje tz-aware."""
    if time_col not in df.columns:
        return df
    try:
        if str(df[time_col].dtype).startswith("datetime64[ns,"):
            df[time_col] = df[time_col].dt.tz_convert("Europe/Warsaw").dt.tz_localize(None)
    except Exception:
        pass
    return df

# --------- Parser argumentów ----------
def build_parser():
    ap = argparse.ArgumentParser(description="Scalanie pomiarów, prognozy i pogody w jeden plik.")
    ap.add_argument("--backtest", required=True, help="Plik z pomiarami (WAQI lub backtest CSV).")
    ap.add_argument("--prediction", required=True, help="Plik z predykcją (CSV).")
    ap.add_argument("--weather", required=True, help="Plik z pogodą (WAQI lub merged_hourly.csv).")
    ap.add_argument("--time-col", default="timestamp", help="Kolumna czasu (domyślnie: timestamp).")
    ap.add_argument("--coalesce-hist", action="store_true", help="Dopełnij historię prognozą tylko w przyszłości.")
    ap.add_argument("--out", required=True, help="Ścieżka wyjściowa CSV.")
    ap.add_argument("--sep", default=None, help="Separator CSV (auto jeśli brak).")
    ap.add_argument("--encoding", default="utf-8", help="Kodowanie CSV (domyślnie utf-8).")
    ap.add_argument("--pollutant", default="pm10", choices=["pm10", "pm25"],
                     help="Które zanieczyszczenie scalamy — steruje nazwami kolumn "
                          "(pm10_true/pm10_pred/pm10_hist albo pm25_true/pm25_pred/pm25_hist). "
                          "Reszta logiki (scalanie pomiaru+prognozy+pogody, interpolacja) jest identyczna.")
    return ap

# --------- MAIN ----------
def main():
    args = build_parser().parse_args()
    back_path = Path(args.backtest)
    pred_path = Path(args.prediction)
    weather_path = Path(args.weather)
    out_path = Path(args.out)

    pol = args.pollutant  # "pm10" albo "pm25"
    col_true, col_pred, col_hist = f"{pol}_true", f"{pol}_pred", f"{pol}_hist"
    # WAQI dla Słupska raportuje tylko PM10 — fallback z pliku pogodowego ma sens
    # wyłącznie dla PM10, dla PM2.5 nie ma czym uzupełniać.
    use_waqi_fallback = (pol == "pm10")

    if not back_path.exists():
        raise FileNotFoundError(f"Brak pliku pomiarów: {back_path}")
    if not pred_path.exists():
        raise FileNotFoundError(f"Brak pliku predykcji: {pred_path}")
    if not weather_path.exists():
        raise FileNotFoundError(f"Brak pliku pogody: {weather_path}")

    # --- 1) Pomiar (WAQI / backtest) ---
    df_true = read_csv_robust(back_path, sep=args.sep, encoding=args.encoding)
    df_true = normalize(df_true)
    df_true = df_true.dropna(subset=["timestamp"]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df_true = unify_time(df_true, "timestamp")
    # Obsługa formatu backtest CSV (y_true/y_pred) generowanego przez backtest_pm10.py
    if pol not in df_true.columns and "y_true" in df_true.columns:
        df_true[pol] = pd.to_numeric(df_true["y_true"], errors="coerce")
    df_true[col_true] = pd.to_numeric(df_true.get(pol, np.nan), errors="coerce")

    # --- 2) Predykcja ---
    df_pred = read_csv_robust(pred_path, sep=args.sep, encoding=args.encoding)
    df_pred = normalize(df_pred)
    df_pred = df_pred.dropna(subset=["timestamp"]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df_pred = unify_time(df_pred, "timestamp")
    df_pred[col_pred] = pd.to_numeric(df_pred.get(col_pred, np.nan), errors="coerce")
    # Jeśli backtest CSV zawiera historyczne predykcje (y_pred), uzupełnij df_pred
    if "y_pred" in df_true.columns:
        bt_as_pred = df_true[["timestamp"]].copy()
        bt_as_pred[col_pred] = pd.to_numeric(df_true["y_pred"], errors="coerce")
        # Połącz: priorytet df_pred (nowe predykcje przyszłości), uzupełnienie z backtestu
        df_pred = (
            pd.concat([bt_as_pred, df_pred])
            .drop_duplicates(subset=["timestamp"], keep="last")
            .sort_values("timestamp")
        )

    # --- 3) Pogoda ---
    df_weather = read_csv_robust(weather_path, sep=args.sep, encoding=args.encoding)
    df_weather = normalize(df_weather)
    df_weather = df_weather.dropna(subset=["timestamp"]).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df_weather = unify_time(df_weather, "timestamp")
    df_weather = to_numeric_cols(df_weather, ["temp", "rh", "pressure", "wind"])

    # Wyodrębnij pomiar z pliku pogodowego (WAQI) — uzupełni *_true tam, gdzie brakuje
    # (tylko dla PM10 — patrz use_waqi_fallback powyżej)
    waqi_fallback = None
    if use_waqi_fallback and "pm10" in df_weather.columns and df_weather["pm10"].notna().any():
        waqi_fallback = df_weather[["timestamp", "pm10"]].copy()
        waqi_fallback = waqi_fallback[waqi_fallback["pm10"].notna()]

    # Ogranicz weather do samych kolumn pogodowych,
    # aby nie nadpisać *_true/*_pred podczas łączenia:
    weather_cols = ["timestamp"] + [c for c in ["temp", "rh", "pressure", "wind"] if c in df_weather.columns]
    df_weather = df_weather[weather_cols]

    # --- MERGE: pomiar + predykcja (nearest, tolerance=1h) ---
    merged_hist = pd.merge_asof(
        df_true[["timestamp", col_true]].sort_values("timestamp"),
        df_pred[["timestamp", col_pred]].sort_values("timestamp"),
        on="timestamp",
        direction="nearest",
        tolerance=pd.Timedelta("1h"),
    )
    # *_hist (prognoza na punktach historii)
    merged_hist[col_hist] = merged_hist[col_pred]
    merged_hist["error"] = merged_hist[col_hist] - merged_hist[col_true]

    # --- Przyszłość: wszystko po last_true ---
    if merged_hist[col_true].notna().any():
        last_true_ts = merged_hist["timestamp"][merged_hist[col_true].notna()].max()
    else:
        last_true_ts = merged_hist["timestamp"].min()

    future_sel = df_pred[df_pred["timestamp"] > last_true_ts][["timestamp", col_pred]].copy()
    future_sel[col_true] = np.nan
    future_sel[col_hist] = future_sel[col_pred] if args.coalesce_hist else np.nan
    future_sel["error"] = np.nan

    df_pm = pd.concat([merged_hist, future_sel], ignore_index=True)\
             .drop_duplicates(subset=["timestamp"]).sort_values("timestamp")

    # --- Dołącz pogodę (merge_asof z tolerancją 1h) ---
    df_final = pd.merge_asof(
        df_pm.sort_values("timestamp"),
        df_weather.sort_values("timestamp"),
        on="timestamp",
        direction="nearest",
        tolerance=pd.Timedelta("1h"),
    )

    # --- Uzupełnij *_true danymi WAQI (tylko PM10, jeśli mamy je z pliku pogodowego) ---
    if waqi_fallback is not None and not waqi_fallback.empty:
        df_final = pd.merge_asof(
            df_final.sort_values("timestamp"),
            waqi_fallback.rename(columns={"pm10": "_waqi_fallback"}).sort_values("timestamp"),
            on="timestamp",
            direction="nearest",
            tolerance=pd.Timedelta("1h"),
        )
        # Tam gdzie *_true jest NaN, wstaw wartość z WAQI
        mask = df_final[col_true].isna() & df_final["_waqi_fallback"].notna()
        df_final.loc[mask, col_true] = df_final.loc[mask, "_waqi_fallback"]
        df_final = df_final.drop(columns=["_waqi_fallback"])
        # Przelicz błąd ze zaktualizowanymi pomiarami
        df_final["error"] = df_final[col_hist] - df_final[col_true]

    # --- Resample do pełnej siatki godzinowej i interpolacja luk ---
    if not df_final.empty:
        ts_min = df_final["timestamp"].min()
        ts_max = df_final["timestamp"].max()
        full_idx = pd.date_range(start=ts_min, end=ts_max, freq="h")
        df_final = (
            df_final
            .drop_duplicates(subset=["timestamp"])
            .set_index("timestamp")
            .reindex(full_idx)
        )
        df_final.index.name = "timestamp"
        # Pomiary (*_true): interpolacja liniowa (max 6h ciągłej przerwy)
        df_final[col_true] = df_final[col_true].interpolate(method="linear", limit=6)
        # Predykcja i historia: pełna interpolacja liniowa (model daje ciągłe wyjście)
        for col in [col_pred, col_hist]:
            if col in df_final.columns:
                df_final[col] = df_final[col].interpolate(method="linear", limit=None)
        # Przelicz błąd po interpolacji
        df_final["error"] = df_final[col_hist] - df_final[col_true]
        # Pogoda: interpolacja (max 6h)
        for col in ["temp", "rh", "pressure", "wind"]:
            if col in df_final.columns:
                df_final[col] = df_final[col].interpolate(method="linear", limit=6)
        df_final = df_final.reset_index()

    # --- Zapis ---
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(out_path, index=False)

    # --- Raport do konsoli ---
    print(f"[OK] Zapisano plik łączony z pogodą ({pol}): {out_path} (wierszy: {len(df_final)})")
    print(f"[INFO] Kolumny: {list(df_final.columns)}")
    if df_final[col_pred].notna().any():
        first_future = df_final["timestamp"][df_final[col_true].isna()].min()
        print(f"[INFO] Pierwsza prognoza (bez pomiaru) od: {first_future}")

if __name__ == "__main__":
    main()
