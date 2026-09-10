"""Wrapper kompatybilnościowy dla `train_pm10.py`.
Przyjmuje stare argumenty (`--in`, `--model`, `--target`) i wywołuje `train_pm10.main()`.
Jeżeli podano `--in` / `--model`, nadpisuje odpowiednie zmienne w module `train_pm10`.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

# Upewnij się, że moduł train_pm10 jest importowalny
sys.path.append(str(Path(__file__).resolve().parent.parent))
import train_pm10


def main():
    ap = argparse.ArgumentParser(description="Compatibility wrapper -> train_pm10.py")
    ap.add_argument("--in", dest="infile", help="(opcjonalne) plik cech (ignored by train_pm10 unless exists)")
    ap.add_argument("--model", dest="model", help="(opcjonalne) ścieżka zapisu modelu")
    ap.add_argument("--target", dest="target", default="pm10", help="(opcjonalne) target (domyślnie 'pm10')")
    args = ap.parse_args()

    # Obsługa --target (na razie wspieramy tylko pm10)
    if args.target and args.target.lower() not in ("pm10", "pm_10"):
        raise SystemExit(f"Nieobsługiwany target: {args.target} — użyj 'pm10'.")

    # Gdy podano --in, nadpisz wartość FEATURES_PM10_CSV w train_pm10
    if args.infile:
        train_pm10.FEATURES_PM10_CSV = Path(args.infile)

    # Gdy podano --model, nadpisz MODEL_PATH
    if args.model:
        train_pm10.MODEL_PATH = Path(args.model)

    # Wywołaj bezpośrednio funkcję main z train_pm10
    train_pm10.main()


if __name__ == "__main__":
    main()
