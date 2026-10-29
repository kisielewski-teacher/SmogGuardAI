# -*- coding: utf-8 -*-
"""
demo_check.py — kontrola gotowosci przed prezentacja (np. przed komisja konkursowa).

Sprawdza po kolei, czy wszystko, co bedzie potrzebne na scenie, dziala i jest swieze:
dane, prognoza z przedzialem niepewnosci, modele, wyniki testow poza proba, wykresy do slajdow,
panel w przegladarce i dostep do internetu (zywe dane). Na koniec drukuje liczby do wypowiedzi.

Uzycie: py src/demo_check.py     (albo dwuklik: demo_check.bat)
Kod wyjscia: 0 = wszystko gotowe, 1 = jest co najmniej jeden blad (FAIL); ostrzezenia (WARN) go nie zmieniaja.
"""
import sys
import time
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parents[1]
DOCS = BASE / "docs"
results = []


def report(status: str, text: str) -> None:
    results.append(status)
    mark = {"OK": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[status]
    print(f"{mark} {text}")


def age_hours(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 3600


def check_data():
    p = BASE / "data" / "merged_hourly.csv"
    if not p.exists():
        report("FAIL", "Brak data/merged_hourly.csv — uruchom run_full_pipeline.bat")
        return
    df = pd.read_csv(p, parse_dates=["timestamp"])
    last_pm = df.loc[df["PM10"].notna(), "timestamp"].max()
    age = (pd.Timestamp.now() - last_pm).total_seconds() / 3600
    span = f"{df['timestamp'].min():%Y-%m-%d} .. {df['timestamp'].max():%Y-%m-%d}"
    if age <= 6:
        report("OK", f"Dane: {len(df)} godzin ({span}); ostatni pomiar PM10 sprzed {age:.1f} h")
    elif age <= 48:
        report("WARN", f"Ostatni pomiar PM10 sprzed {age:.0f} h — przed prezentacja uruchom run_pipeline_scheduled.bat")
    else:
        report("FAIL", f"Dane sa stare ({age:.0f} h) — uruchom run_pipeline_scheduled.bat")
    if "kierunek_wiatru" in df.columns and df["kierunek_wiatru"].notna().mean() > 0.9:
        report("OK", "Kierunek wiatru obecny w danych (rozeta wiatrow zadziala)")
    else:
        report("WARN", "Brak kierunku wiatru w danych — zakladka 'Roza wiatrow' bedzie pusta")


def check_forecast():
    p = BASE / "outputs" / "pm10_all_latest.csv"
    if not p.exists():
        report("FAIL", "Brak outputs/pm10_all_latest.csv — uruchom run_pipeline_scheduled.bat")
        return
    d = pd.read_csv(p, parse_dates=["timestamp"])
    last_true = d.loc[d["pm10_true"].notna(), "timestamp"].max()
    fut = d[d["timestamp"] > last_true]
    if len(fut) >= 60:
        report("OK", f"Prognoza na przyszlosc: {len(fut)} godzin (do {fut['timestamp'].max():%d.%m %H:%M})")
    else:
        report("FAIL", f"Prognoza ma tylko {len(fut)} godzin przyszlosci")
    if {"pm10_pred_low", "pm10_pred_high"} <= set(d.columns) and fut["pm10_pred_low"].notna().any():
        w = (fut["pm10_pred_high"] - fut["pm10_pred_low"]).mean()
        report("OK", f"Przedzial niepewnosci obecny (srednia szerokosc {w:.0f} ug/m3)")
    else:
        report("WARN", "Brak przedzialu niepewnosci w prognozie — uruchom: py src/direct_forecast.py train --max-age-hours 0")


def check_models():
    p = BASE / "models" / "pm10_direct.pkl"
    if p.exists():
        report("OK", f"Model bezposredni (LightGBM) istnieje, wiek {age_hours(p):.0f} h")
    else:
        report("FAIL", "Brak models/pm10_direct.pkl — uruchom: py src/direct_forecast.py train --max-age-hours 0")
    if (BASE / "models" / "pm10_pipeline.pkl").exists():
        report("OK", "Model pomocniczy (Random Forest) istnieje")
    else:
        report("WARN", "Brak models/pm10_pipeline.pkl (pomocniczy RF) — zakladka z dopasowaniem do historii moze byc pusta")


def check_accuracy():
    p = BASE / "outputs" / "pm10_horizon_accuracy.csv"
    if not p.exists():
        report("FAIL", "Brak outputs/pm10_horizon_accuracy.csv — uruchom run_full_pipeline.bat")
        return
    a = pd.read_csv(p)
    if "test_start" not in a.columns:
        report("WARN", "Plik dokladnosci pochodzi ze starego audytu W PROBIE — uruchom run_full_pipeline.bat")
        return
    r24, r72 = a[a["horizon_h"] == 24].iloc[0], a[a["horizon_h"] == 72].iloc[0]
    report("OK", f"Audyt poza proba ({a['test_start'].iloc[0]} .. {a['test_end'].iloc[0]}, wiek {age_hours(p):.0f} h)")
    print(f"        LICZBY DO WYPOWIEDZI: za 24 h blad {r24['mae']:.1f} ug/m3 (bez zmian: {r24['baseline_mae']:.1f}, "
          f"poprawa {r24['improvement_pct']:.0f}%); za 72 h blad {r72['mae']:.1f} (bez zmian: {r72['baseline_mae']:.1f}, "
          f"poprawa {r72['improvement_pct']:.0f}%)")
    iv = BASE / "outputs" / "experiment_intervals_step12.csv"
    if iv.exists():
        c = pd.read_csv(iv)["interval_coverage"].mean() * 100
        print(f"        Przedzial 80%: zmierzone pokrycie {c:.0f}% (poza proba)")


def check_docs():
    need = [DOCS / "Jak_poprawilismy_prognoze.md", DOCS / "Streszczenie_dla_komisji.md", DOCS / "Scenariusz_prezentacji.md",
            DOCS / "wykres_porownanie_metod.png", DOCS / "wykres_pm10_a_kierunek_wiatru.png"]
    missing = [p.name for p in need if not p.exists()]
    if missing:
        report("FAIL", "Brakuje materialow w docs/: " + ", ".join(missing))
    else:
        report("OK", "Materialy dla komisji i wykresy do slajdow sa w docs/")


def check_panel():
    try:
        r = requests.get("http://localhost:8501/_stcore/health", timeout=4)
        if r.status_code == 200 and r.text.strip() == "ok":
            report("OK", "Panel dziala: http://localhost:8501")
        else:
            report("WARN", f"Panel odpowiada nietypowo ({r.status_code})")
    except requests.RequestException:
        report("WARN", "Panel nie dziala — uruchom: py -m streamlit run app/app_extended_multi.py (albo run_full_pipeline.bat)")


def check_internet():
    try:
        r = requests.get("https://api.gios.gov.pl/pjp-api/v1/rest/station/findAll", params={"size": 1}, timeout=8)
        report("OK" if r.status_code == 200 else "WARN", f"Dostep do API GIOS (zywe dane): HTTP {r.status_code}")
    except requests.RequestException:
        report("WARN", "Brak dostepu do API GIOS — pokaz panel na zapisanych danych (dziala bez internetu)")


def main() -> int:
    try:
        version = (BASE / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        version = "?"
    print(f"=== Kontrola gotowosci SmogGuardAI v{version} przed prezentacja ===\n")
    for fn in (check_data, check_forecast, check_models, check_accuracy, check_docs, check_panel, check_internet):
        try:
            fn()
        except Exception as e:  # noqa: BLE001 - kontrola ma zawsze dojsc do konca
            report("FAIL", f"{fn.__name__}: {type(e).__name__}: {str(e)[:120]}")
    n_fail, n_warn = results.count("FAIL"), results.count("WARN")
    print(f"\nPodsumowanie: {results.count('OK')} OK, {n_warn} ostrzezen, {n_fail} bledow.")
    print("GOTOWE do prezentacji." if not n_fail else "NIE GOTOWE — napraw bledy [FAIL] powyzej.")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
