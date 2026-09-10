
# -*- coding: utf-8 -*-
r"""
make_all_forecasts.py  (wersja bez f-stringów)

Jednym poleceniem uruchamia trening i prognozowanie dla: PM10, PM2.5, NO2, O3.

Użycie (z poziomu katalogu projektu):
    py src\make_all_forecasts.py               # train + predict
    py src\make_all_forecasts.py --train-only  # tylko trening
    py src\make_all_forecasts.py --predict-only# tylko prognozy
    py src\make_all_forecasts.py --continue-on-error
"""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

# Ścieżki zgodne z układem: C:\...\air3\src\*.py, dane w ..\data\, modele w ..\models\
SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
DATA = ROOT / 'data'
MODELS = ROOT / 'models'

# Skrypty są w folderze src
TRAIN_SCRIPTS = ['train_pm10.py', 'train_pm25.py', 'train_no2.py', 'train_o3.py']
PREDICT_SCRIPTS = ['predict_pm10.py', 'predict_pm25.py', 'predict_no2.py', 'predict_o3.py']

# Pełne ścieżki do skryptów w src/
TRAIN_SCRIPTS = [SRC / s for s in TRAIN_SCRIPTS]
PREDICT_SCRIPTS = [SRC / s for s in PREDICT_SCRIPTS]

FORECAST_FILES = [DATA/'forecast_pm10.csv', DATA/'forecast_pm25.csv', DATA/'forecast_no2.csv', DATA/'forecast_o3.csv']
MERGED_PATH = DATA / 'merged_hourly.csv'

def run_cmd(cmd):
    # cmd = [sys.executable, '<pełna_ścieżka_do_skryptu.py>']
    print("\n>>> RUN: " + ' '.join([str(x) for x in cmd]))
    try:
        # cwd = ROOT, aby skrypty miały dostęp do data/models
        proc = subprocess.run(cmd, cwd=str(ROOT), check=True)
        return proc.returncode
    except subprocess.CalledProcessError as e:
        print("[ERROR] Komenda zakończona kodem " + str(e.returncode) + ": " + ' '.join([str(x) for x in cmd]))
        return e.returncode

def main():
    parser = argparse.ArgumentParser(description='Train + Predict for PM10/PM2.5/NO2/O3')
    parser.add_argument('--train-only', action='store_true')
    parser.add_argument('--predict-only', action='store_true')
    parser.add_argument('--continue-on-error', action='store_true')
    args = parser.parse_args()

    # Upewnij się, że data/ i models/ istnieją
    DATA.mkdir(exist_ok=True)
    MODELS.mkdir(exist_ok=True)

    # Sprawdzenie danych (dla treningu)
    if not MERGED_PATH.exists() and (args.train_only or not args.predict_only):
        print('[ERROR] Brak pliku danych: ' + str(MERGED_PATH))
        if not args.predict_only:
            sys.exit(2)

    overall_rc = 0

    def batch_run(scripts):
        nonlocal overall_rc
        ok = True
        for s in scripts:
            rc = run_cmd([sys.executable, str(s)])
            if rc != 0:
                ok = False
                overall_rc = rc
                if not args.continue_on_error:
                    return False
        return ok

    if args.predict_only:
        print('[STAGE] Tylko prognozowanie')
        ok = batch_run(PREDICT_SCRIPTS)
        if ok:
            # jeśli prognozy się powiodły — scalamy PM10 do outputs/pm10_all_latest.csv
            print('[STAGE] Scalanie wyników PM10 -> outputs/pm10_all_latest.csv')
            run_cmd([sys.executable, str(SRC / 'merge_pm10_results.py'),
                     '--backtest', str(DATA / 'aqicn_slupsk_data.csv'),
                     '--prediction', str(ROOT / 'outputs' / 'pm10_pred_latest.csv'),
                     '--weather', str(DATA / 'aqicn_slupsk_data.csv'),
                     '--time-col', 'timestamp',
                     '--coalesce-hist',
                     '--out', str(ROOT / 'outputs' / 'pm10_all_latest.csv')])
    elif args.train_only:
        print('[STAGE] Tylko trening')
        ok = batch_run(TRAIN_SCRIPTS)
        if not ok and not args.continue_on_error:
            sys.exit(overall_rc or 1)
    else:
        print('[STAGE] Trening modeli')
        ok = batch_run(TRAIN_SCRIPTS)
        if not ok and not args.continue_on_error:
            sys.exit(overall_rc or 1)
        print('[STAGE] Prognozowanie')
        ok = batch_run(PREDICT_SCRIPTS)
        if ok:
            print('[STAGE] Scalanie wyników PM10 -> outputs/pm10_all_latest.csv')
            run_cmd([sys.executable, str(SRC / 'merge_pm10_results.py'),
                     '--backtest', str(DATA / 'aqicn_slupsk_data.csv'),
                     '--prediction', str(ROOT / 'outputs' / 'pm10_pred_latest.csv'),
                     '--weather', str(DATA / 'aqicn_slupsk_data.csv'),
                     '--time-col', 'timestamp',
                     '--coalesce-hist',
                     '--out', str(ROOT / 'outputs' / 'pm10_all_latest.csv')])

    print('\n[SUMMARY] Pliki forecast:')
    for f in FORECAST_FILES:
        if f.exists():
            try:
                with f.open('r', encoding='utf-8') as fh:
                    n = sum(1 for _ in fh) - 1
                print(' - ' + str(f.relative_to(ROOT)) + '  (wierszy: ' + str(max(n, 0)) + ')')
            except Exception:
                print(' - ' + str(f.relative_to(ROOT)) + '  (istnieje)')
        else:
            print(' - ' + str(f.relative_to(ROOT)) + '  (BRAK)')

    sys.exit(overall_rc)

if __name__ == '__main__':
    main()
