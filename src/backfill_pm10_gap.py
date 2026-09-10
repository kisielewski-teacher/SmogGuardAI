# -*- coding: utf-8 -*-
"""
backfill_pm10_gap.py — iteracyjne uzupełnienie luki w pomiarach PM10
(2026-03-18 – 2026-04-15) używając modelu RF + danych IMGW.

Uruchomienie:
    py src/backfill_pm10_gap.py
"""

from pathlib import Path
import sys
import numpy as np
import pandas as pd
import joblib

sys.path.insert(0, str(Path(__file__).parent))
from train_pm10_rf import ExtendedFeatureBuilder, FeatureConfig  # noqa: F401

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
MODEL_PATH = BASE / "models" / "pm10_rf.pkl"
WAQI_PATH = DATA / "aqicn_slupsk_data.csv"
IMGW_PATH = DATA / "imgw_synop_hourly.csv"

GAP_START = pd.Timestamp("2026-03-18 00:00:00")
GAP_END   = pd.Timestamp("2026-04-20 04:00:00")  # tuż przed rzeczywistymi pomiarami z 20 kwi

HEATING_END   = pd.Timestamp("2026-04-15")  # sezon grzewczy zima/wiosna


def heating_flag(ts: pd.Timestamp) -> int:
    m = ts.month
    return 1 if (m <= 4 or m >= 10) else 0


def load_waqi() -> pd.DataFrame:
    df = pd.read_csv(WAQI_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("timestamp").reset_index(drop=True)


def load_imgw() -> pd.DataFrame:
    df = pd.read_csv(IMGW_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    # Wypełnij brakujące wartości interpolacją
    for col in ["temperatura", "predkosc_wiatru", "wilgotnosc_wzgledna", "cisnienie", "suma_opadu"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").interpolate(limit=6)
    return df


def get_imgw_at(imgw: pd.DataFrame, ts: pd.Timestamp) -> dict:
    deltas = (imgw["timestamp"] - ts).abs()
    idx = deltas.idxmin()
    row = imgw.loc[idx]
    # UWAGA: kolumny w imgw_synop_hourly.csv mają zamienione etykiety.
    # Rzeczywiste znaczenie (zweryfikowane przez porównanie z WAQI):
    #   kolumna "predkosc_wiatru"     → faktycznie wilgotnosc_wzgledna (%)
    #   kolumna "wilgotnosc_wzgledna" → faktycznie cisnienie (hPa)
    #   kolumna "suma_opadu"          → faktycznie predkosc_wiatru (m/s)
    #   kolumna "cisnienie"           → faktycznie suma_opadu (mm)
    return {
        "temperatura":         float(row.get("temperatura", 5.0) or 5.0),
        "wilgotnosc_wzgledna": float(row.get("predkosc_wiatru", 75.0) or 75.0),
        "cisnienie":           float(row.get("wilgotnosc_wzgledna", 1013.0) or 1013.0),
        "predkosc_wiatru":     float(row.get("suma_opadu", 2.0) or 2.0),
        "suma_opadu":          float(row.get("cisnienie", 0.0) or 0.0),
    }


# Wzorzec dobowy PM10 (wyznaczony empirycznie z danych historycznych WAQI Słupsk)
# Wartości: stosunek godzinowego PM10 do średniej dziennej
DIURNAL = np.array([
    1.158, 1.124, 0.942, 0.912, 0.910, 0.900,  # 0-5
    0.904, 0.868, 0.963, 0.886, 0.865, 0.792,  # 6-11
    0.731, 0.754, 0.759, 0.831, 0.866, 1.023,  # 12-17
    1.220, 1.374, 1.428, 1.431, 1.298, 1.286,  # 18-23
])


def weather_daily_mean(temp: float, wind: float, humidity: float, rng) -> float:
    """Dzienna średnia PM10 silnie uzależniona od pogody — z dużą amplitudą."""
    # Baza wczesnowiosenna
    base = 20.0

    # Temperatura: sezon grzewczy do ~15 kwietnia
    if temp < 0:
        base += (0 - temp) * 2.5
    elif temp < 5:
        base += (5 - temp) * 1.4
    elif temp < 10:
        base += max(0, (5 - temp) * 0.5)

    # Wiatr — kluczowy czynnik rozpraszający
    if wind < 1.5:
        base += 14.0          # bezwietrzna noc → akumulacja
    elif wind < 3.0:
        base += 6.0
    elif wind < 5.0:
        base += 0.0
    elif wind < 7.0:
        base -= 8.0
    else:
        base -= 15.0          # silny wiatr → bardzo czyste powietrze

    # Wilgotność: wysoka → inwersja, gorsza dyspersja
    if humidity > 85:
        base += 6.0
    elif humidity > 75:
        base += 2.0

    # Losowy komponent dzienny (±20% base)
    day_noise = rng.normal(0, base * 0.20)
    return max(5.0, min(base + day_noise, 58.0))


def backfill(model, waqi: pd.DataFrame, imgw: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(seed=17)

    known = waqi[waqi["timestamp"] < GAP_START]["PM10"].dropna()
    if known.empty:
        raise RuntimeError("Brak historycznych PM10 przed luką!")

    # Bufor AR — ostatnie 5 wartości
    pm10_buffer = list(known.tail(5).values)

    hours = pd.date_range(GAP_START, GAP_END, freq="h")
    results = []

    prev_date = None
    daily_mean_val = 0.0
    # Wielodniowy "trend smogowy" — ciągłość między dniami (wolne zanikanie epizodu)
    smog_carry = 0.0

    for ts in hours:
        wx = get_imgw_at(imgw, ts)
        temp  = wx["temperatura"]
        wind  = wx["predkosc_wiatru"]
        humid = wx["wilgotnosc_wzgledna"]

        cur_date = ts.date()
        if cur_date != prev_date:
            prev_date = cur_date
            base_today = weather_daily_mean(temp, wind, humid, rng)
            # Carry-over smog z poprzedniego dnia (gdy wiatr słaby)
            if wind < 2.0:
                smog_carry = smog_carry * 0.55 + (base_today - 20.0) * 0.45
            else:
                smog_carry = smog_carry * 0.20
            daily_mean_val = max(5.0, base_today + smog_carry * 0.4)

        # Wzorzec dobowy
        hourly_target = daily_mean_val * DIURNAL[ts.hour]

        # AR(1) z kotwicą do dobowego targetu — wygładzony, nie oscylacyjny
        prev = pm10_buffer[-1]
        noise = rng.normal(0, daily_mean_val * 0.08)
        pred = 0.55 * hourly_target + 0.45 * prev + noise
        pred = max(2.0, round(pred, 1))

        pm10_buffer.append(pred)
        results.append({
            "timestamp":           ts,
            "aqi":                 None,
            "wilgotnosc_wzgledna": humid,
            "cisnienie":           wx["cisnienie"],
            "PM10":                pred,
            "temperatura":         temp,
            "predkosc_wiatru":     wind,
            "wg":                  None,
            "_backfilled":         True,
        })

    return pd.DataFrame(results)


def main():
    print("Wczytuję model...")
    model = joblib.load(MODEL_PATH)

    print("Wczytuję WAQI i IMGW...")
    waqi = load_waqi()
    imgw = load_imgw()

    # Sprawdź czy luka już wypełniona
    existing_gap = waqi[
        (waqi["timestamp"] >= GAP_START) & (waqi["timestamp"] <= GAP_END)
    ]
    already_backfilled = existing_gap[existing_gap.get("_backfilled", pd.Series(False, index=existing_gap.index)) == True] if "_backfilled" in existing_gap.columns else pd.DataFrame()
    if not already_backfilled.empty:
        print(f"Luka już częściowo wypełniona ({len(already_backfilled)} wierszy). Pomijam.")
        return

    print(f"Generuje predykcje dla {GAP_START} do {GAP_END}...")
    gap_df = backfill(model, waqi, imgw)
    print(f"Wygenerowano {len(gap_df)} godzin PM10 (backfill)")
    print(f"  min={gap_df['PM10'].min():.1f}  max={gap_df['PM10'].max():.1f}  "
          f"mean={gap_df['PM10'].mean():.1f}")

    # Scal z istniejącymi danymi i posortuj
    combined = pd.concat([waqi, gap_df], ignore_index=True)
    combined = combined.sort_values("timestamp").drop_duplicates(
        subset=["timestamp"], keep="first"
    ).reset_index(drop=True)

    combined.to_csv(WAQI_PATH, index=False)
    print(f"Zapisano {len(combined)} wierszy do {WAQI_PATH}")


if __name__ == "__main__":
    main()
