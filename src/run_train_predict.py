
# -*- coding: utf-8 -*-
"""
src/run_train_predict.py — prosty wrapper uruchamiający cały pipeline
(zaimplementowany w pliku run_full_pipeline.bat).
Obsługuje zarówno PM10 jak i PM2.5.

Uruchom (z katalogu projektu):
    py src/run_train_predict.py

Skrypt jedynie wywołuje batch `run_full_pipeline.bat`, dlatego nie ma tu
szczegółowej logiki. Przyciskiem możesz zmienić go na własny wariant lub
przemodelować, ale domyślnie korzysta z tego samego mechanizmu co skrypt
Windowsowy.

Uwagi:
- Wymaga pliku `run_full_pipeline.bat` w katalogu głównym projektu.
- Batch wykonuje łącznie: fetch → merge → features → train → predict →
  backtest → merge, dla PM10 i PM2.5.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd


# Ustal root projektu (fallback na CWD, gdy __file__ niedostępne)
try:
    ROOT = Path(__file__).resolve().parents[1]
except Exception:
    ROOT = Path.cwd()
SRC = ROOT / "src"


def run_cmd(args_list: list[str], verbose: bool = True) -> int:
    """Uruchom podproces i (opcjonalnie) wypisz komendę."""
    if verbose:
        try:
            import shlex as _sh
            print("[CMD]", " ".join(_sh.quote(a) for a in args_list))
        except Exception:
            print("[CMD]", " ".join(args_list))
    proc = subprocess.run(args_list, check=True)
    return proc.returncode


def ensure_rows(csv_path: Path) -> int:
    """Zwróć liczbę wierszy w CSV (bez nagłówka). Rzuć błąd, jeśli plik nie istnieje."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Brak pliku: {csv_path}")
    try:
        df = pd.read_csv(csv_path)
        return len(df)
    except Exception:
        with csv_path.open("r", encoding="utf-8", errors="ignore") as f:
            return max(sum(1 for _ in f) - 1, 0)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Pipeline: features→train→predict→merge")
    ap.add_argument("--merged", default=str(ROOT / "data/merged_hourly.csv"))
    ap.add_argument("--features-out", default=str(ROOT / "data/feature_table.csv"))
    ap.add_argument("--model", default=str(ROOT / "outputs/pm10_model.joblib"))
    ap.add_argument("--pred-out", default=str(ROOT / "outputs/pm10_pred_latest.csv"))
    ap.add_argument("--backtest-out", default=str(ROOT / "outputs/pm10_backtest_latest.csv"))
    ap.add_argument("--all-latest-out", default=str(ROOT / "outputs/pm10_all_latest.csv"))
    ap.add_argument("--target", default="pm10")
    ap.add_argument("--lags", nargs="+", type=int, default=[1, 3, 6, 12, 24])
    ap.add_argument("--rolling-win", nargs="+", type=int, default=[6, 12, 24])
    ap.add_argument("--min-rows", type=int, default=72, help="Minimalna liczba wierszy do treningu")
    ap.add_argument("--skip-train", action="store_true", help="Pomiń trening (użyj istniejącego modelu)")
    ap.add_argument(
        "--coalesce-hist",
        action="store_true",
        help="Uzupełnij brakujące pm10_hist predykcją tylko w przyszłości (etap MERGE)",
    )
    ap.add_argument("--time-col", default="timestamp")
    ap.add_argument("--verbose", action="store_true")
    return ap


def main() -> None:
    args = build_parser().parse_args()

    # rather than implementing all steps in Python, we reuse the
    # Windows batch runner `run_full_pipeline.bat` which now handles both
    # PM10 and PM2.5 (fetch, features, train, predict, backtest, merge).
    bat = ROOT / "run_full_pipeline.bat"
    if not bat.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku pipeline: {bat}")
    print(f"[INFO] Uruchamiam pełny pipeline z: {bat}")
    rc = run_cmd([str(bat)])
    if rc != 0:
        print(f"[WARN] pipeline zwrócił kod: {rc}")
    return
