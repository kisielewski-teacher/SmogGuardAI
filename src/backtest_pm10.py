
# -*- coding: utf-8 -*-
"""
backtest_pm10.py — generuje predykcje out-of-sample (walk-forward) na pełnej historii,
bez nadpisywania poprzednich plików (wersjonowanie po dacie/godzinie).

Użycie (przykład):
python backtest_pm10.py \
  --csv-path data/merged_hourly.csv \
  --time-col timestamp \
  --target PM10 \
  --model models/pm10_pipeline.pkl \
  --out-dir outputs
"""

import argparse
import os
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from utils_features import resolve_best_target_alias

# --- Kompatybilność unpickle (alias klas z treningu do __main__) ---
# Upewnij się, że 'src' jest na ścieżce importów; jeśli odpalasz `py src\backtest_pm10.py`,
# to i tak powinno działać. W razie potrzeby odkomentuj poniższe 2 linie:
# import sys
# sys.path.append(os.path.join(os.getcwd(), 'src'))

import sys
try:
    # Zakładamy, że plik train_pm10_rf.py jest w tym samym katalogu co ten skrypt (src/)
    from train_pm10_rf import ExtendedFeatureBuilder, FeatureConfig
    sys.modules['__main__'].ExtendedFeatureBuilder = ExtendedFeatureBuilder
    sys.modules['__main__'].FeatureConfig = FeatureConfig
except Exception:
    # Jeśli import się nie uda, spróbujemy dalej — joblib.load może zadziałać,
    # ale jeśli nie, zgłosimy czytelny błąd przy load.
    pass


def parse_args():
    p = argparse.ArgumentParser(description="Backtest PM10 (walk-forward) na pełnej historii")
    p.add_argument("--csv-path", type=str, default="data/merged_hourly.csv")
    p.add_argument("--time-col", type=str, default="timestamp")
    p.add_argument("--target", type=str, default="PM10")
    p.add_argument("--model", type=str, default="models/pm10_pipeline.pkl")
    p.add_argument("--sep", type=str, default=",")
    p.add_argument("--encoding", type=str, default="utf-8")
    p.add_argument("--out-dir", type=str, default="outputs")
    return p.parse_args()


def main():
    args = parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    # Slug do nazwy pliku wyjściowego, ustalony PRZED ewentualną podmianą args.target
    # na alias (np. 'PM2.5' -> 'pm25_median') — inaczej plik zawsze nazywałby się
    # 'pm10_backtest_*.csv' nawet dla PM2.5, co myliłoby run_full_pipeline.bat
    # (szuka najnowszego pm10_backtest_*.csv i pm25_backtest_*.csv osobno).
    target_slug = args.target.lower().replace(".", "").replace("_", "")

    df = pd.read_csv(args.csv_path, sep=args.sep, encoding=args.encoding)
    if args.time_col not in df.columns:
        raise ValueError(f"Brak kolumny czasu: {args.time_col}")

    # Jeżeli podany target nie istnieje, spróbujmy dopasować heurystycznie (np. PM10_x / PM10_y)
    if args.target not in df.columns:
        candidates = [c for c in df.columns if args.target.lower() in c.lower()]
        if candidates:
            chosen = candidates[0]
            print(f"[WARN] Nie znaleziono kolumny '{args.target}' — używam '{chosen}' zamiast tego")
            args.target = chosen
        else:
            raise ValueError(f"Brak kolumny celu: {args.target}")

    df = df.sort_values(args.time_col).reset_index(drop=True)

    # Napraw kolumnę celu: jeśli ma mniej danych niż jej alias (PM10_x/PM10_y/
    # pm10_mean albo PM2.5_x/PM2.5_y/pm25_mean), użyj aliasu — działa dla
    # dowolnego zanieczyszczenia, patrz utils_features.resolve_best_target_alias.
    TARGET_MIN_ROWS = 10
    TARGET_MAX_PHYSICAL = 500.0
    target_count = df[args.target].notna().sum() if args.target in df.columns else 0
    best_alias, best_count = resolve_best_target_alias(df, args.target, min_rows=TARGET_MIN_ROWS)
    if best_alias is not None:
        df[args.target] = pd.to_numeric(df[best_alias], errors="coerce")
        target_count = best_count
        print(f"[INFO] Kolumna celu '{args.target}' zastąpiona danymi z '{best_alias}' ({best_count} wierszy)")
    # Odrzuć artefakty merge (np. ciśnienie w kolumnie PM10, literówki w PM2.5)
    outliers = (df[args.target] > TARGET_MAX_PHYSICAL).sum()
    if outliers > 0:
        df.loc[df[args.target] > TARGET_MAX_PHYSICAL, args.target] = np.nan
        print(f"[INFO] Wyzerowano {outliers} wierszy z {args.target} > {TARGET_MAX_PHYSICAL} (artefakty)")

    # Wczytanie pipeline'u z obsługą ewentualnego błędu __main__.ExtendedFeatureBuilder
    try:
        pipe = joblib.load(args.model)
    except AttributeError as e:
        raise RuntimeError(
            "Nie udało się wczytać pipeline'u. Jeżeli widzisz błąd typu "
            "'module __main__ has no attribute ExtendedFeatureBuilder', upewnij się, że:\n"
            " - plik 'train_pm10_rf.py' leży w katalogu 'src' i jest importowalny,\n"
            " - uruchamiasz skrypt z katalogu projektu (CWD = C:\\Programy\\SmogGuardAI\\air3),\n"
            " - ewentualnie dodaj 'src' do sys.path (odkomentuj w kodzie odpowiednią linię)."
        ) from e

    # Warmup = max(lag, window) wyciągnięte z featurera
    fb = pipe.named_steps.get("features")
    warmup = 0
    if fb is not None:
        warmup = max(
            (max(fb.config.lags) if fb.config.lags else 0),
            (max(fb.config.rolling_windows) if fb.config.rolling_windows else 0),
        )

    # Jeżeli pipeline oczekuje innej nazwy kolumny celu (np. 'PM10' albo 'PM2.5')
    # niż ta w CSV, upewnij się że ta kolumna ma wystarczająco dużo danych po naszej naprawie.
    if fb is not None:
        expected_target = getattr(fb.config, "target_col", None)
        if expected_target:
            exp_count = df[expected_target].notna().sum() if expected_target in df.columns else 0
            if exp_count < TARGET_MIN_ROWS:
                # Skopiuj naprawiony args.target do expected_target
                if args.target in df.columns:
                    df[expected_target] = df[args.target]
                    print(f"[INFO] Skopiowano naprawioną kolumnę '{args.target}' -> '{expected_target}' (dla featurera)")
                else:
                    best_alias, _ = resolve_best_target_alias(df, expected_target, min_rows=1)
                    if best_alias is not None:
                        df[expected_target] = df[best_alias]
                        print(f"[INFO] Skopiowano kolumnę '{best_alias}' -> '{expected_target}' (dla featurera)")
                    else:
                        raise RuntimeError(f"Brak kolumny z danymi celu do backtestu.")

    preds = []
    times = []
    y_true = []

    # Walk-forward: na każdym kroku przewidujemy bieżący wiersz, używając pełnej historii do bieżącej chwili.
    # Cały chunk (nie tylko ostatni wiersz) trzeba podać do pipe.predict(), bo ExtendedFeatureBuilder
    # liczy lagi/rolling przez shift()/rolling() na przekazanym DataFrame — pojedynczy wiersz
    # dawałby same NaN w cechach lag/rolling i model przestałby realnie korzystać z historii PM10.
    for i in range(warmup, len(df)):
        # Wystarczy `warmup` wierszy historii przed bieżącym, żeby poprawnie
        # policzyć najdłuższy lag/rolling — ograniczamy okno, żeby backtest
        # nie robił się O(n^2) na długiej historii.
        chunk = df.iloc[max(0, i - warmup): i + 1].copy()
        y_hat = pipe.predict(chunk)[-1]
        preds.append(y_hat)
        times.append(df.loc[i, args.time_col])
        y_true.append(df.loc[i, args.target])

    out = pd.DataFrame({
        args.time_col: times,
        "y_true": y_true,
        "y_pred": preds,
    })
    out["error"] = out["y_pred"] - out["y_true"]

    # Metryki zbiorcze
    mae = float(np.mean(np.abs(out["error"])))
    rmse = float(np.sqrt(np.mean(out["error"] ** 2)))
    nonzero = out["y_true"] != 0
    mape = float(np.mean(np.abs(out.loc[nonzero, "error"] / out.loc[nonzero, "y_true"])) * 100) if nonzero.any() else float("nan")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(args.out_dir, f"{target_slug}_backtest_{stamp}.csv")
    out.to_csv(out_path, index=False)

    print("Zapisano backtest do:", out_path)
    print(f"MAE={mae:.3f}, RMSE={rmse:.3f}, MAPE={mape:.1f}%")


if __name__ == "__main__":
    main()
