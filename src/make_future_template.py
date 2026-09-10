# -*- coding: utf-8 -*-
"""
make_future_template.py — generuje szablon pliku future_hours.csv na horyzont H (godzin),
na podstawie historii (kolumny i ostatni znany timestamp).

Użycie:
python make_future_template.py \
  --history-csv data/merged_hourly.csv \
  --time-col timestamp \
  --target PM10 \
  --hours 24 \
  --out data/future_hours.csv

Domyślnie przepisuje kolumny meteo/kategorie z historii i wypełnia wartościami NaN.
Możesz dodać --copy-last, aby skopiować ostatnie dostępne wartości meteo do wszystkich przyszłych godzin.
"""

import argparse
import pandas as pd
import numpy as np
from datetime import timedelta


def parse_args():
    p = argparse.ArgumentParser(description="Generator szablonu future_hours.csv")
    p.add_argument("--history-csv", type=str, default="data/merged_hourly.csv")
    p.add_argument("--time-col", type=str, default="timestamp")
    p.add_argument("--target", type=str, default="PM10")
    p.add_argument("--hours", type=int, default=24, help="Horyzont w godzinach")
    p.add_argument("--sep", type=str, default=",")
    p.add_argument("--encoding", type=str, default="utf-8")
    p.add_argument("--copy-last", action="store_true", help="Skopiuj ostatnie meteo do przyszłości (zamiast NaN)")
    p.add_argument("--out", type=str, default="data/future_hours.csv")
    return p.parse_args()


def main():
    args = parse_args()
    df = pd.read_csv(args.history_csv, sep=args.sep, encoding=args.encoding)
    if args.time_col not in df.columns:
        raise ValueError(f"Brak kolumny czasu: {args.time_col}")

    # Posortuj i wyznacz start przyszłości
    df = df.sort_values(args.time_col).reset_index(drop=True)
    last_ts = pd.to_datetime(df.loc[len(df)-1, args.time_col])
    future_index = pd.date_range(start=last_ts + pd.Timedelta(hours=1), periods=args.hours, freq='h')

    # Kolumny do przepisania: wszystkie poza targetem (celu nie ma w przyszłości)
    cols = [c for c in df.columns if c != args.target]

    # Przygotuj pustą ramkę z NaN
    fut = pd.DataFrame(index=range(args.hours))
    fut[args.time_col] = future_index
    for c in cols:
        if c == args.time_col:
            continue
        fut[c] = np.nan

    if args.copy_last:
        last_row = df.iloc[-1]
        for c in cols:
            if c == args.time_col:
                continue
            fut[c] = last_row.get(c, np.nan)

    fut.to_csv(args.out, index=False)
    print(f"Utworzono szablon: {args.out}")
    print(f"Zakres: {future_index[0]} .. {future_index[-1]}")


if __name__ == "__main__":
    main()
