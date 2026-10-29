# -*- coding: utf-8 -*-
"""
backtest_horizon.py — audyt dokładności prognozy PM10 W FUNKCJI HORYZONTU (h=1..N godzin).

W przeciwieństwie do backtest_pm10.py (który liczy tylko błąd 1-krokowy, zawsze
na bazie PRAWDZIWYCH opóźnień PM10), ten skrypt odtwarza dokładnie to, co robi
predict_pm10.py w produkcji: rekurencyjną (autoregresywną) predykcję wieloetapową,
gdzie prognoza z kroku h służy jako "lag" dla kroku h+1. Dzięki temu pokazuje
REALNY wzrost błędu wraz z długością horyzontu — potrzebny, żeby uczciwie
ocenić, czy sensowne jest wydłużanie prognozy do 48h/72h.

Metodologia (rolling-origin evaluation):
- Dla wielu punktów startowych ("origin") w historii, cofamy się i puszczamy
  model do przodu o --max-horizon godzin, krok po kroku, dokładnie jak w
  iterative_future_predict() z predict_pm10.py.
- Pogoda w oknie przyszłości NIE jest prognozowana — używamy prawdziwej,
  zarejestrowanej pogody (bo backtestu z historycznymi prognozami pogody nie
  da się odtworzyć). To założenie "idealnej prognozy pogody" oznacza, że
  realny błąd w produkcji (gdzie pogoda też jest tylko prognozą) będzie
  nieco WYŻSZY niż to, co pokaże ten audyt — audyt mierzy dolną granicę błędu.
- PM10 (target) jest maskowany na każdym kroku w przyszłości — model go nie
  widzi, korzysta tylko z własnych wcześniejszych predykcji (tak jak w realu).

Użycie:
    py src/backtest_horizon.py --csv-path data/merged_hourly.csv \
        --model models/pm10_pipeline.pkl --max-horizon 72 --step-hours 24 \
        --out outputs/pm10_horizon_accuracy.csv
"""
import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_pm10_rf import ExtendedFeatureBuilder, FeatureConfig  # noqa: E402
from utils_features import resolve_best_target_alias  # noqa: E402
sys.modules["__main__"].ExtendedFeatureBuilder = ExtendedFeatureBuilder
sys.modules["__main__"].FeatureConfig = FeatureConfig

TARGET_MAX_PHYSICAL = 500.0  # µg/m3 — wyżej to artefakt scalania, nie realny pomiar


def fix_target_column(df: pd.DataFrame, target: str) -> pd.DataFrame:
    """Ten sam fallback co w train_pm10_rf.py/predict_pm10.py: jeśli kolumna celu
    (PM10, PM2.5, ...) ma mało danych, użyj lepszego aliasu — merge_hourly.py
    potrafi zostawić kanoniczną kolumnę prawie pustą i przenieść realne dane
    do PM10_x/PM10_y/pm10_mean (albo analogicznie dla PM2.5)."""
    best_alias, _ = resolve_best_target_alias(df, target)
    if best_alias is not None:
        df[target] = pd.to_numeric(df[best_alias], errors="coerce")
    outliers = (df[target] > TARGET_MAX_PHYSICAL).sum()
    if outliers > 0:
        df.loc[df[target] > TARGET_MAX_PHYSICAL, target] = np.nan
    return df


def run_one_origin(df: pd.DataFrame, origin_idx: int, warmup: int, horizon: int,
                    fb, model, time_col: str, target_col: str) -> list[dict]:
    hist_start = max(0, origin_idx - warmup - 5)
    working = df.iloc[hist_start: origin_idx + 1].copy().reset_index(drop=True)
    future_true = df.iloc[origin_idx + 1: origin_idx + 1 + horizon].copy().reset_index(drop=True)

    if len(future_true) < horizon or future_true[target_col].isna().any():
        return []
    if working[target_col].tail(warmup).isna().any():
        return []

    # Baseline "naiwny" (persystencja): "jutro = teraz, bez zmian" — ostatnia
    # znana wartość powielona na cały horyzont. To standardowy punkt odniesienia
    # w prognozowaniu szeregów czasowych — model AI musi go wyraźnie pokonać,
    # inaczej nie wnosi żadnej wartości ponad zgadywanie "bez zmian".
    baseline_val = float(df.loc[origin_idx, target_col])

    expected_features = list(getattr(model, "feature_names_in_", fb.get_feature_names_out()))
    records = []

    for h in range(1, horizon + 1):
        true_val = float(future_true.loc[h - 1, target_col])
        new_row = future_true.iloc[h - 1].copy()
        new_row[target_col] = np.nan  # model nie może "podejrzeć" prawdziwej wartości

        working = pd.concat([working, pd.DataFrame([new_row])], ignore_index=True)
        X_feat = fb.transform(working)
        X_row = X_feat.tail(1).reindex(columns=expected_features, fill_value=0.0)
        pred = float(model.predict(X_row)[0])
        pred = max(0.0, pred)

        working.loc[working.index[-1], target_col] = pred  # feed-back dla kolejnego lagu

        records.append({
            "origin": df.loc[origin_idx, time_col],
            "horizon_h": h,
            "y_true": true_val,
            "y_pred": pred,
            "error": pred - true_val,
            "baseline_pred": baseline_val,
            "baseline_error": baseline_val - true_val,
        })
    return records


def main():
    ap = argparse.ArgumentParser(description="Audyt dokładności PM10 w funkcji horyzontu prognozy")
    ap.add_argument("--csv-path", default="data/merged_hourly.csv")
    ap.add_argument("--model", default="models/pm10_pipeline.pkl")
    ap.add_argument("--time-col", default="timestamp")
    ap.add_argument("--target", default="PM10")
    ap.add_argument("--max-horizon", type=int, default=72)
    ap.add_argument("--step-hours", type=int, default=24, help="Odstęp między punktami startowymi (origins)")
    ap.add_argument("--out", default="outputs/pm10_horizon_accuracy.csv")
    ap.add_argument("--out-raw", default=None, help="Opcjonalnie: zapisz też surowe błędy per-origin/h")
    ap.add_argument("--jobs", type=int, default=-1,
                    help="Liczba procesów równoległych (punkty startowe są niezależne); 1 = bez równoległości, -1 = wszystkie rdzenie")
    args = ap.parse_args()

    df = pd.read_csv(args.csv_path, parse_dates=[args.time_col])
    df = df.sort_values(args.time_col).reset_index(drop=True)
    df = fix_target_column(df, args.target)

    pipe = joblib.load(args.model)
    fb = pipe.named_steps["features"]
    model = pipe.named_steps["model"]
    target_col = fb.config.target_col
    if target_col != args.target:
        df[target_col] = df[args.target]

    warmup = max(max(fb.config.lags) if fb.config.lags else 0,
                 max(fb.config.rolling_windows) if fb.config.rolling_windows else 0)

    n = len(df)
    origins = list(range(warmup + 5, n - args.max_horizon, args.step_hours))
    print(f"[INFO] Liczba punktów startowych (origins): {len(origins)}")

    # Pojedynczy wiersz do RandomForest z n_jobs=-1 tylko traci czas na start wątków,
    # a równoległość i tak dają procesy po punktach startowych.
    if hasattr(model, "n_jobs"):
        model.n_jobs = 1

    def _one(o):
        return run_one_origin(df, o, warmup, args.max_horizon, fb, model, args.time_col, target_col)

    if args.jobs == 1 or len(origins) < 2:
        results = [_one(o) for o in origins]
    else:
        results = joblib.Parallel(n_jobs=args.jobs, verbose=0)(joblib.delayed(_one)(o) for o in origins)

    all_records = []
    skipped = 0
    for recs in results:
        if not recs:
            skipped += 1
            continue
        all_records.extend(recs)

    print(f"[INFO] Pominięto {skipped}/{len(origins)} origins (braki danych w oknie)")
    if not all_records:
        print("[ERR] Brak wyników — sprawdź dane wejściowe / horyzont.")
        sys.exit(1)

    rec_df = pd.DataFrame(all_records)
    if args.out_raw:
        rec_df.to_csv(args.out_raw, index=False)

    summary = rec_df.groupby("horizon_h").apply(
        lambda g: pd.Series({
            "mae": np.mean(np.abs(g["error"])),
            "rmse": np.sqrt(np.mean(g["error"] ** 2)),
            "bias": np.mean(g["error"]),
            "baseline_mae": np.mean(np.abs(g["baseline_error"])),
            "baseline_rmse": np.sqrt(np.mean(g["baseline_error"] ** 2)),
            "n": len(g),
        }),
        include_groups=False,
    ).reset_index()
    summary["improvement_pct"] = 100 * (1 - summary["mae"] / summary["baseline_mae"])

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.out, index=False)

    print("\n===== Dokładność prognozy w funkcji horyzontu (h) — model vs baseline (\"bez zmian\") =====")
    for h in [1, 3, 6, 12, 24, 36, 48, 60, 72]:
        row = summary[summary["horizon_h"] == h]
        if not row.empty:
            r = row.iloc[0]
            print(f"h+{h:>3}h : MAE={r['mae']:6.2f}  baseline_MAE={r['baseline_mae']:6.2f}  "
                  f"popraw.={r['improvement_pct']:+5.1f}%  bias={r['bias']:+6.2f}  (n={int(r['n'])})")
    print(f"\n[OK] Zapisano pełne wyniki do: {args.out}")


if __name__ == "__main__":
    main()
