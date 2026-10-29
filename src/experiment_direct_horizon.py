# -*- coding: utf-8 -*-
"""
experiment_direct_horizon.py — prognoza "bezposrednia" zamiast "rekurencyjnej".

Obecny model przewiduje 1 godzine do przodu, a prognoze na 72 h buduje w petli:
wynik z godziny h trafia jako "wczorajsza wartosc" do godziny h+1. Kazdy maly blad
jest wiec powielany w kolejnych krokach (kumuluje sie).

Tutaj, dla KAZDEGO horyzontu h = 1..72 uczymy OSOBNY model, ktory od razu odpowiada
na pytanie: "jakie bedzie PM10 za h godzin, jesli znam wszystko do TERAZ?".
Nic sie nie kumuluje, bo nie ma petli.

Ocena jest uczciwa: model uczy sie na danych sprzed --test-start, a testujemy na
danych od --test-start (nigdy niewidzianych), w tych samych punktach startowych co
w experiment_history_length.py, wiec wyniki mozna wprost porownac z prognoza
rekurencyjna i z prognoza "bez zmian".

Uzycie:
    py src/experiment_direct_horizon.py [--test-start 2026-01-01] [--train-years 4]
Wynik: outputs/experiment_direct_horizon.csv
"""
import argparse
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from direct_forecast import (  # noqa: E402  (to samo co w produkcji)
    LGB_PARAMS, TARGET, apply_interval, fit_interval_h, future_weather_features, load_grid, neighbor_features,
    origin_features, target_time_features, upwind_features,
)

BASE = Path(__file__).resolve().parents[1]


def valid_origins(df, test_start, max_h, step, warmup=24):
    """Te same punkty startowe i warunki co w backtest_horizon.py (pelne okno przed i pelna przyszlosc)."""
    s = df[TARGET].to_numpy()
    first = int(np.searchsorted(df.index.values, np.datetime64(test_start)))
    out = []
    for o in range(first, len(df) - max_h, step):
        if np.isnan(s[o - warmup + 1:o + 1]).any() or np.isnan(s[o + 1:o + 1 + max_h]).any():
            continue
        out.append(o)
    return out


def main():
    ap = argparse.ArgumentParser(description="Prognoza bezposrednia (osobny model na kazdy horyzont) vs rekurencyjna")
    ap.add_argument("--csv-path", default=str(BASE / "data" / "merged_hourly.csv"))
    ap.add_argument("--test-start", default="2026-01-01")
    ap.add_argument("--test-days", type=int, default=0,
                    help="Jesli > 0: okres testowy = ostatnie N dni danych (aktualizuje sie sam z biegiem czasu)")
    ap.add_argument("--train-years", type=float, default=4.0)
    ap.add_argument("--max-horizon", type=int, default=72)
    ap.add_argument("--step-hours", type=int, default=48)
    ap.add_argument("--intervals", action="store_true",
                    help="Dodatkowo ucz modele kwantylowe (10%% i 90%%) i zmierz pokrycie przedzialu poza proba")
    ap.add_argument("--calib-days", type=int, default=365, help="Ile ostatnich dni uczacych zostawic na kalibracje przedzialu")
    ap.add_argument("--future-weather", choices=["none", "perfect", "perfect_smooth", "noisy"], default="none",
                    help="Pogoda w chwili prognozowanej: none = bez, perfect = idealna prognoza (GORNA granica zysku), "
                         "noisy = idealna + szum o typowej wielkosci bledu prognozy (zalozenie, patrz NOISE)")
    ap.add_argument("--neighbors", action="store_true",
                    help="Dodaj PM10 z sasiednich stacji GIOS (data/neighbors_pm10.csv) jako cechy")
    ap.add_argument("--upwind", action="store_true",
                    help="Dodaj PM10 ze stacji lezacych pod wiatr (wymaga data/neighbors_pm10.csv)")
    ap.add_argument("--no-wind", action="store_true", help="Bez cech kierunku wiatru (porownanie A/B).")
    ap.add_argument("--n-estimators", type=int, default=300)
    ap.add_argument("--out", default=str(BASE / "outputs" / "experiment_direct_horizon.csv"))
    ap.add_argument("--out-raw", default=None, help="Zapisz bledy kazdego punktu startowego (do testu parowego)")
    args = ap.parse_args()

    df = load_grid(Path(args.csv_path))
    if args.test_days > 0:
        test_start = df[TARGET].last_valid_index().normalize() - pd.Timedelta(days=args.test_days)
    else:
        test_start = pd.Timestamp(args.test_start)
    train_start = test_start - pd.Timedelta(days=int(round(365.25 * args.train_years)))
    feats = origin_features(df, use_wind=not args.no_wind)
    if args.neighbors:
        feats = feats.join(neighbor_features(df.index))
    if args.upwind:
        feats = feats.join(upwind_features(df))
    origins = valid_origins(df, test_start, args.max_horizon, args.step_hours)
    print(f"[INFO] Punktow startowych w tescie: {len(origins)}; trening od {train_start.date()} do {test_start.date()}")
    y = df[TARGET]

    rows = []
    raw_rows = []
    for h in range(1, args.max_horizon + 1):
        X = pd.concat([feats, target_time_features(df.index, h)], axis=1)
        if args.future_weather != "none":
            noise = None
            if args.future_weather == "noisy":
                # ZALOZENIE (typowe bledy prognoz numerycznych na 1-3 doby; nie mierzone u nas):
                # temperatura 1,5 st. C, cisnienie 2 hPa, wilgotnosc 10 pp., wiatr 1,5 m/s, kierunek 40 st.
                noise = {"temperatura": 1.5, "cisnienie": 2.0, "wilgotnosc_wzgledna": 10.0,
                         "predkosc_wiatru": 1.5, "kierunek_wiatru": 40.0}
            smooth = 12 if args.future_weather == "perfect_smooth" else 0
            X = pd.concat([X, future_weather_features(df, h, noise, smooth=smooth)], axis=1)
        y_h = y.shift(-h)                       # wartosc PM10 za h godzin
        train_mask = (df.index >= train_start) & (df.index + pd.Timedelta(hours=h) < test_start) & y_h.notna().to_numpy()
        model = lgb.LGBMRegressor(n_jobs=-1, **{**LGB_PARAMS, "n_estimators": args.n_estimators})
        model.fit(X[train_mask], y_h[train_mask])
        cover = width = np.nan
        cover_raw = np.nan
        if args.intervals:
            iv = fit_interval_h(df.index.values, X, y_h, h, train_start, test_start, calib_days=args.calib_days)
            point = np.maximum(model.predict(X.iloc[origins]), 0.0)
            truth = y_h.iloc[origins].to_numpy()
            lo, hi = apply_interval(iv, X.iloc[origins], point)
            raw_lo, raw_hi = apply_interval((iv[0], iv[1], 0.0), X.iloc[origins], point)
            cover = float(np.mean((truth >= lo) & (truth <= hi)))
            cover_raw = float(np.mean((truth >= raw_lo) & (truth <= raw_hi)))
            width = float(np.mean(hi - lo))
        Xo = X.iloc[origins]
        pred = np.maximum(model.predict(Xo), 0.0)
        true = y_h.iloc[origins].to_numpy()
        base = df[TARGET].iloc[origins].to_numpy()   # "bez zmian": wartosc z chwili startu
        err = pred - true
        if args.out_raw:
            raw_rows.append(pd.DataFrame({"origin": df.index[origins], "h": h, "y_true": true,
                                          "pred": pred, "base": base}))
        rows.append({"horizon_h": h, "mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err ** 2))),
                     "bias": float(np.mean(err)), "baseline_mae": float(np.mean(np.abs(base - true))),
                     "baseline_rmse": float(np.sqrt(np.mean((base - true) ** 2))),
                     "test_start": str(test_start.date()), "test_end": str(df.index[origins[-1]].date()),
                     "n": len(origins), "train_rows": int(train_mask.sum()),
                     "interval_coverage": cover, "interval_coverage_raw": cover_raw, "interval_width": width})
        if h in (1, 6, 12, 24, 48, 72):
            r = rows[-1]
            if args.intervals:
                print(f"      przedzial 10-90%: pokrycie po kalibracji={r['interval_coverage']*100:.0f}% "
                      f"(surowe {r['interval_coverage_raw']*100:.0f}%, cel 80%), szerokosc={r['interval_width']:.1f}")
            print(f"h+{h:>2}h: MAE direct={r['mae']:.2f}  baseline={r['baseline_mae']:.2f}  "
                  f"bias={r['bias']:+.2f}  (train={r['train_rows']})")

    if args.out_raw:
        pd.concat(raw_rows, ignore_index=True).to_csv(args.out_raw, index=False)
    res = pd.DataFrame(rows)
    res["improvement_pct"] = 100 * (1 - res["mae"] / res["baseline_mae"])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(args.out, index=False)
    print(f"\n[OK] Zapisano: {args.out}")


if __name__ == "__main__":
    main()
