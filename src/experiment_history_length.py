# -*- coding: utf-8 -*-
"""
experiment_history_length.py — czy dluzsza historia uczenia poprawia prognoze PM10?

Uczciwy test (bez "podgladania"): model uczy sie WYLACZNIE na danych sprzed
--test-start, a jest oceniany na danych od --test-start, ktorych nigdy nie widzial.
Porownujemy rozne dlugosci historii uczenia (np. pol roku, 1, 2, 3, 4 lata).

Dla kazdego okna liczymy:
- blad 1-krokowy (prognoza na nastepna godzine, MAE/RMSE),
- blad prognozy wieloetapowej (rekurencyjnej, tak jak w produkcji) dla h=1..72 h
  w wybranych godzinach doby, zawsze w porownaniu z prognoza "bez zmian" (persystencja).

Uzycie:
    py src/experiment_history_length.py [--test-start 2026-01-01] [--windows 0.5 1 2 3 4]
Wynik: outputs/experiment_history_length.csv (+ podsumowanie na ekranie).
"""
import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_pm10_rf import ExtendedFeatureBuilder, FeatureConfig  # noqa: E402
from backtest_horizon import run_one_origin  # noqa: E402

BASE = Path(__file__).resolve().parents[1]
PM10_MAX_PHYSICAL = 500.0
TARGET = "PM10"
LAGS = (1, 3, 6, 12, 24)
ROLLING = (3, 6, 12, 24)


def load_prepared(csv_path: Path) -> pd.DataFrame:
    """To samo przygotowanie danych co w train_pm10_rf.train(): bez kolumn-proxy celu."""
    df = pd.read_csv(csv_path, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    leaky_prefixes = ("pm10", "pm25", "aqi", "no2", "o3")
    leaky = [c for c in df.columns
             if c.lower() != TARGET.lower() and c != "timestamp"
             and any(c.lower().replace("_", "").replace(".", "").startswith(p) for p in leaky_prefixes)]
    df = df.drop(columns=leaky)
    df.loc[df[TARGET] > PM10_MAX_PHYSICAL, TARGET] = np.nan
    return df


def fit_window(df: pd.DataFrame, train_start: pd.Timestamp, test_start: pd.Timestamp, n_estimators: int):
    train_df = df[(df["timestamp"] >= train_start) & (df["timestamp"] < test_start)].dropna(subset=[TARGET])
    cfg = FeatureConfig(time_col="timestamp", target_col=TARGET, lags=LAGS, rolling_windows=ROLLING)
    pipe = Pipeline([
        ("features", ExtendedFeatureBuilder(cfg)),
        ("model", RandomForestRegressor(n_estimators=n_estimators, min_samples_leaf=10,
                                        random_state=42, n_jobs=-1)),
    ])
    pipe.fit(train_df, train_df[TARGET].astype(float))
    return pipe, len(train_df)


def one_step_errors(pipe, df, test_start):
    test = df[df["timestamp"] >= test_start].dropna(subset=[TARGET])
    # kontekst: 24 h historii przed testem, zeby lagi na poczatku testu byly prawdziwe
    ctx_start = df.index[df["timestamp"] >= test_start][0] - 30
    block = df.iloc[ctx_start:].reset_index(drop=True)
    pred = pipe.predict(block)
    m = (block["timestamp"] >= test_start) & block[TARGET].notna()
    err = pred[m.values] - block.loc[m, TARGET].values
    return float(np.mean(np.abs(err))), float(np.sqrt(np.mean(err ** 2))), int(m.sum())


def horizon_errors(pipe, df, test_start, max_horizon, step_hours, jobs, raw_path=None):
    fb = pipe.named_steps["features"]
    model = pipe.named_steps["model"]
    model.n_jobs = 1
    warmup = max(max(LAGS), max(ROLLING))
    first = int(df.index[df["timestamp"] >= test_start][0])
    origins = list(range(first, len(df) - max_horizon, step_hours))

    def _one(o):
        return run_one_origin(df, o, warmup, max_horizon, fb, model, "timestamp", TARGET)

    results = joblib.Parallel(n_jobs=jobs)(joblib.delayed(_one)(o) for o in origins)
    recs = [r for res in results for r in res]
    rec = pd.DataFrame(recs)
    if rec.empty:
        return {}
    if raw_path:
        # ten sam format co experiment_direct_horizon.py --out-raw (do compare_experiments.py)
        rec.rename(columns={"horizon_h": "h", "y_pred": "pred", "baseline_pred": "base"})[
            ["origin", "h", "y_true", "pred", "base"]].to_csv(raw_path, index=False)
    out = {}
    for h in (1, 6, 24, 48, 72):
        g = rec[rec["horizon_h"] == h]
        if g.empty:
            continue
        out[f"mae_h{h}"] = float(np.mean(np.abs(g["error"])))
        out[f"baseline_mae_h{h}"] = float(np.mean(np.abs(g["baseline_error"])))
        out[f"bias_h{h}"] = float(np.mean(g["error"]))
    out["origins_used"] = int(rec["origin"].nunique())
    return out


def main():
    ap = argparse.ArgumentParser(description="Wplyw dlugosci historii uczenia na dokladnosc prognozy PM10")
    ap.add_argument("--csv-path", default=str(BASE / "data" / "merged_hourly.csv"))
    ap.add_argument("--test-start", default="2026-01-01")
    ap.add_argument("--windows", type=float, nargs="+", default=[0.5, 1, 2, 3, 4], help="dlugosci historii w latach")
    ap.add_argument("--n-estimators", type=int, default=200)
    ap.add_argument("--max-horizon", type=int, default=72)
    ap.add_argument("--step-hours", type=int, default=48)
    ap.add_argument("--jobs", type=int, default=-1)
    ap.add_argument("--out", default=str(BASE / "outputs" / "experiment_history_length.csv"))
    ap.add_argument("--out-raw-prefix", default=None,
                    help="Zapisz bledy punktow startowych jako <prefiks>_<lata>y.csv (do testu parowego)")
    args = ap.parse_args()

    df = load_prepared(Path(args.csv_path))
    test_start = pd.Timestamp(args.test_start)
    rows = []
    for years in args.windows:
        train_start = test_start - pd.Timedelta(days=int(round(365.25 * years)))
        if train_start < df["timestamp"].min():
            print(f"[INFO] Okno {years} lat siega przed poczatek danych ({df['timestamp'].min().date()}) — skracam.")
            train_start = df["timestamp"].min()
        pipe, n_train = fit_window(df, train_start, test_start, args.n_estimators)
        mae1, rmse1, n_test = one_step_errors(pipe, df, test_start)
        row = {"years_of_history": years, "train_start": train_start.date(), "train_rows": n_train,
               "mae_1step": mae1, "rmse_1step": rmse1, "test_rows": n_test}
        raw_path = f"{args.out_raw_prefix}_{years:g}y.csv" if args.out_raw_prefix else None
        row.update(horizon_errors(pipe, df, test_start, args.max_horizon, args.step_hours, args.jobs, raw_path))
        rows.append(row)
        print(f"[OK] {years} lat: train={n_train} wierszy, MAE 1-krok={mae1:.2f}, "
              f"MAE h+24={row.get('mae_h24', float('nan')):.2f} (baseline {row.get('baseline_mae_h24', float('nan')):.2f}), "
              f"MAE h+72={row.get('mae_h72', float('nan')):.2f} (baseline {row.get('baseline_mae_h72', float('nan')):.2f})")

    res = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(args.out, index=False)
    print(f"\n[OK] Zapisano: {args.out}")


if __name__ == "__main__":
    main()
