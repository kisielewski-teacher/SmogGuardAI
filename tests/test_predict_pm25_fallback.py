import os
import sys
import shutil
import subprocess
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "models" / "pm25_rf.pkl"
MERGED_PATH = REPO_ROOT / "data" / "merged_hourly.csv"
FORECAST_PATH = REPO_ROOT / "data" / "forecast_pm25.csv"


def _backup(p: Path):
    if p.exists():
        shutil.copy(p, p.with_suffix(p.suffix + ".bak"))


def _restore(p: Path):
    bak = p.with_suffix(p.suffix + ".bak")
    if bak.exists():
        if p.exists():
            p.unlink()
        shutil.move(bak, p)


def test_predict_pm25_fallback_creates_forecast():
    # backup files that test will touch
    _backup(MODEL_PATH)
    _backup(MERGED_PATH)
    if FORECAST_PATH.exists():
        shutil.copy(FORECAST_PATH, FORECAST_PATH.with_suffix('.bak'))

    try:
        # prepare minimal merged_hourly.csv (no PM2.5 values)
        MERGED_PATH.parent.mkdir(parents=True, exist_ok=True)
        MERGED_PATH.write_text("timestamp,PM10\n2026-01-01 00:00:00,10\n2026-01-01 01:00:00,11\n")

        # ensure model does NOT exist so predict_pm25 triggers fallback
        if MODEL_PATH.exists():
            MODEL_PATH.unlink()

        # run script
        res = subprocess.run([sys.executable, "src/predict_pm25.py"], cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert res.returncode == 0, f"predict_pm25 failed: {res.stderr}\n{res.stdout}"

        # check forecast file
        assert FORECAST_PATH.exists(), "forecast_pm25.csv was not created"
        df = pd.read_csv(FORECAST_PATH)
        assert "pm25_pred" in df.columns
        assert len(df) == 24

    finally:
        # restore
        _restore(MODEL_PATH)
        _restore(MERGED_PATH)
        bak = FORECAST_PATH.with_suffix('.bak')
        if bak.exists():
            if FORECAST_PATH.exists():
                FORECAST_PATH.unlink()
            shutil.move(bak, FORECAST_PATH)
