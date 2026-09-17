# -*- coding: utf-8 -*-
"""
estimate_pm25_from_pm10.py — SZACUJE (nie mierzy!) historyczne PM2.5 dla Słupska
na podstawie realnego PM10 (GIOŚ) i sezonowości pogodowej (sezon grzewczy),
skalibrowane na garstce realnych, równoległych pomiarów PM2.5+PM10 z czujników
Syngeos.

PO CO TEN SKRYPT ISTNIEJE:
Syngeos (jedyne lokalne źródło PM2.5 dla Słupska) nie ma API archiwalnego —
tylko bieżący odczyt. Realnych, równoległych pomiarów PM2.5+PM10 mamy więc
tylko 12 (po odrzuceniu jednego artefaktu). To za mało, żeby wytrenować
Random Forest (próg bezpieczeństwa w train_pm10_rf.py to 72 wiersze), ale
wystarczy, żeby oszacować prosty, interpretowalny współczynnik PM2.5/PM10.

METODOLOGIA (celowo prosta — 12 punktów nie uzasadnia niczego bardziej
skomplikowanego, żeby nie dopasować się do szumu):
1. Weź realne pary (PM2.5, PM10) w tych samych godzinach (Syngeos + GIOŚ).
2. Podziel je na sezon grzewczy (XI–III) i pozostały — bo źródła emisji
   (spalanie) zmieniają relację drobny/gruby pył między sezonami.
3. Współczynnik = MEDIANA PM2.5/PM10 w każdej grupie (odporna na outliery
   przy tak małej próbie).
4. Zastosuj współczynnik do PEŁNEJ historii realnego PM10, żeby uzyskać
   `PM2.5_estimated` dla każdej godziny.

TO JEST DANE SZACOWANE, NIE POMIAR. Model wytrenowany na tej podstawie
(`train_pm25_bootstrap.bat`/ręcznie z `--csv-path data/merged_hourly_pm25_bootstrap.csv`)
MUSI być oznaczony w dashboardzie/README jako "estymacja", nie "dane
zweryfikowane" — inaczej łamiemy zasadę uczciwości danych przyjętą w tym
projekcie (patrz gios_real_backfill.py, gdzie usunięto dane syntetyczne).
Gdy zbierze się >=72h realnych pomiarów Syngeos, należy przetrenować model
na realnych danych i porzucić ten bootstrap.

Wyjście:
- data/merged_hourly_pm25_bootstrap.csv — kopia merged_hourly.csv z kolumną
  'PM2.5' nadpisaną: realna wartość tam gdzie jest, inaczej oszacowana.
- models/pm25_bootstrap_meta.txt — jawny opis metodologii i współczynników,
  do wyświetlenia w dashboardzie / README.
"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils_features import resolve_best_target_alias  # noqa: E402

BASE = Path(__file__).resolve().parents[1]
MERGED_PATH = BASE / "data" / "merged_hourly.csv"
SYNGEOS_PATH = BASE / "data" / "syngeos_agg.csv"
OUT_CSV = BASE / "data" / "merged_hourly_pm25_bootstrap.csv"
OUT_META = BASE / "models" / "pm25_bootstrap_meta.txt"

PM_MAX_PHYSICAL = 500.0
HEATING_MONTHS = {11, 12, 1, 2, 3}
MIN_CAL_POINTS_PER_GROUP = 3  # poniżej tego mediana grupy jest zbyt niepewna — użyj globalnej


def load_calibration_pairs() -> pd.DataFrame:
    """Realne równoległe pomiary PM2.5 (Syngeos) + PM10 (GIOŚ, z merged_hourly)."""
    sg = pd.read_csv(SYNGEOS_PATH, parse_dates=["timestamp"])
    real = sg[sg.get("pm25_count", 0) > 0].copy()
    real["pm25_mean"] = pd.to_numeric(real["pm25_mean"], errors="coerce")
    real = real[(real["pm25_mean"].notna()) & (real["pm25_mean"].between(0, PM_MAX_PHYSICAL))]

    merged = pd.read_csv(MERGED_PATH, parse_dates=["timestamp"])
    best_alias, _ = resolve_best_target_alias(merged, "PM10")
    pm10_col = best_alias or "PM10"
    m = merged[["timestamp", pm10_col]].rename(columns={pm10_col: "PM10_real"})
    m["PM10_real"] = pd.to_numeric(m["PM10_real"], errors="coerce")

    cal = real.merge(m, on="timestamp", how="left").dropna(subset=["PM10_real"])
    cal = cal[cal["PM10_real"] > 0]  # unikaj dzielenia przez ~0 (śmieciowy współczynnik)
    cal["ratio"] = cal["pm25_mean"] / cal["PM10_real"]
    cal["heating"] = cal["timestamp"].dt.month.isin(HEATING_MONTHS)
    return cal[["timestamp", "pm25_mean", "PM10_real", "ratio", "heating"]]


def compute_ratios(cal: pd.DataFrame) -> dict:
    global_median = float(cal["ratio"].median())
    ratios = {"global": global_median, "n_total": len(cal)}
    for heating in (True, False):
        grp = cal[cal["heating"] == heating]
        key = "heating" if heating else "nonheating"
        if len(grp) >= MIN_CAL_POINTS_PER_GROUP:
            ratios[key] = float(grp["ratio"].median())
        else:
            ratios[key] = global_median  # za mało punktów — nie dziel dalej, użyj globalnej
        ratios[f"{key}_n"] = len(grp)
    return ratios


MIN_ROWS_TO_TRAIN = 72  # ta sama reguła co w train_pm10_rf.py


def main():
    merged_probe = pd.read_csv(MERGED_PATH, parse_dates=["timestamp"])
    real_alias, real_count = resolve_best_target_alias(merged_probe, "PM2.5", min_rows=1)
    real_count = max(real_count, pd.to_numeric(merged_probe.get("PM2.5"), errors="coerce").notna().sum() if "PM2.5" in merged_probe.columns else 0)

    if real_count >= MIN_ROWS_TO_TRAIN:
        # Wystarczająco realnych danych — GRADUACJA: porzuć estymację, ucz na
        # czystych danych rzeczywistych (dokładnie jak PM10). Usuwamy stary plik
        # metadanych bootstrap, żeby dashboard przestał pokazywać ostrzeżenie.
        print(f"[OK] Realnych pomiarów PM2.5: {real_count} (>= {MIN_ROWS_TO_TRAIN}) — "
              f"pomijam estymację, kopiuję czyste dane rzeczywiste do {OUT_CSV.name}.")
        merged_probe.to_csv(OUT_CSV, index=False)
        if OUT_META.exists():
            OUT_META.unlink()
            print(f"[OK] Usunięto {OUT_META.name} (model nie jest już bootstrapem).")
        return

    cal = load_calibration_pairs()
    if len(cal) < 5:
        print(f"[ERR] Tylko {len(cal)} realnych par PM2.5/PM10 do kalibracji — za mało nawet na prosty współczynnik.")
        sys.exit(1)

    ratios = compute_ratios(cal)
    print("[INFO] Kalibracja na realnych parach pomiarowych (Syngeos PM2.5 + GIOŚ PM10):")
    print(cal.to_string(index=False))
    print(f"\n[INFO] Współczynnik PM2.5/PM10 — sezon grzewczy (XI-III, n={ratios['heating_n']}): {ratios['heating']:.3f}")
    print(f"[INFO] Współczynnik PM2.5/PM10 — pozostały okres (n={ratios['nonheating_n']}): {ratios['nonheating']:.3f}")
    print(f"[INFO] Współczynnik globalny (n={ratios['n_total']}): {ratios['global']:.3f}")

    merged = pd.read_csv(MERGED_PATH, parse_dates=["timestamp"])
    best_alias, best_count = resolve_best_target_alias(merged, "PM10")
    pm10_col = best_alias or "PM10"
    pm10_series = pd.to_numeric(merged[pm10_col], errors="coerce")
    heating_mask = merged["timestamp"].dt.month.isin(HEATING_MONTHS)

    estimated = pd.Series(np.nan, index=merged.index, dtype=float)
    estimated[heating_mask] = pm10_series[heating_mask] * ratios["heating"]
    estimated[~heating_mask] = pm10_series[~heating_mask] * ratios["nonheating"]

    # Realne pomiary PM2.5 (tam gdzie są) mają pierwszeństwo przed estymacją.
    best_pm25_alias, best_pm25_count = resolve_best_target_alias(merged, "PM2.5")
    real_pm25 = pd.to_numeric(merged[best_pm25_alias], errors="coerce") if best_pm25_alias else pd.Series(np.nan, index=merged.index)
    real_pm25 = real_pm25.where(real_pm25.between(0, PM_MAX_PHYSICAL))

    final_pm25 = real_pm25.combine_first(estimated)
    is_estimated = real_pm25.isna() & final_pm25.notna()

    out = merged.copy()
    out["PM2.5"] = final_pm25
    out["PM2.5_is_estimated"] = is_estimated
    out.to_csv(OUT_CSV, index=False)

    n_real = int((~is_estimated & final_pm25.notna()).sum())
    n_est = int(is_estimated.sum())
    print(f"\n[OK] Zapisano {OUT_CSV} — PM2.5: {n_real} realnych + {n_est} szacowanych (razem {n_real + n_est}).")

    OUT_META.parent.mkdir(parents=True, exist_ok=True)
    meta_txt = f"""MODEL PM2.5 — BOOTSTRAP NA DANYCH SZACOWANYCH (nie w pełni zweryfikowanych)
=========================================================================
Wygenerowano przez: src/estimate_pm25_from_pm10.py

Dlaczego bootstrap: lokalne źródło PM2.5 dla Słupska (Syngeos) nie ma API
archiwalnego, tylko bieżący odczyt. Zebrano dotąd {ratios['n_total']} realnych,
równoległych pomiarów PM2.5+PM10 — za mało na trening Random Forest (próg: 72).

Metodologia: PM2.5_szacowane = PM10_realne x współczynnik(sezon).
Współczynnik = mediana PM2.5/PM10 z realnych par, osobno dla sezonu
grzewczego i pozostałego okresu (bo spalanie zmienia relację drobny/gruby pył).

Współczynniki:
- sezon grzewczy (XI-III), n={ratios['heating_n']}: {ratios['heating']:.3f}
- pozostały okres, n={ratios['nonheating_n']}: {ratios['nonheating']:.3f}
- globalny (fallback), n={ratios['n_total']}: {ratios['global']:.3f}

Dane treningowe: {n_real} realnych pomiarów PM2.5 + {n_est} godzin szacowanych z PM10.

WAŻNE: to NIE są zweryfikowane pomiary. To statystyczny szacunek z bardzo
małej próby kalibracyjnej (wysoka wariancja: odchylenie std. współczynnika
w sezonie grzewczym = {cal[cal['heating']]['ratio'].std():.2f}, poza sezonem = {cal[~cal['heating']]['ratio'].std():.2f}).
Model wytrenowany na tej podstawie powinien być tak oznaczony w dashboardzie
i zastąpiony modelem na realnych danych, gdy tylko zbierze się >=72h
prawdziwych pomiarów Syngeos (harmonogram godzinowy dokłada je automatycznie).
"""
    OUT_META.write_text(meta_txt, encoding="utf-8")
    print(f"[OK] Zapisano opis metodologii: {OUT_META}")


if __name__ == "__main__":
    main()
