import os
import sys
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "models" / "pm25_rf.pkl"
MERGED_PATH = REPO_ROOT / "data" / "merged_hourly.csv"


def _backup(p: Path):
    if p.exists():
        shutil.copy(p, p.with_suffix(p.suffix + ".bak"))


def _restore(p: Path):
    bak = p.with_suffix(p.suffix + ".bak")
    if bak.exists():
        if p.exists():
            p.unlink()
        shutil.move(bak, p)


def test_train_pm25_skips_with_too_few_rows():
    _backup(MODEL_PATH)
    _backup(MERGED_PATH)

    try:
        # write merged_hourly.csv with <72 PM2.5 samples (simulate scarce data)
        MERGED_PATH.parent.mkdir(parents=True, exist_ok=True)
        merged_csv = "timestamp,PM2.5,PM10\n"
        for i in range(5):
            merged_csv += f"2026-01-01 0{i}:00:00,{i},{10+i}\n"
        MERGED_PATH.write_text(merged_csv)

        # remove existing model to ensure we can detect creation
        if MODEL_PATH.exists():
            MODEL_PATH.unlink()

        res = subprocess.run([sys.executable, "src/train_pm25.py"], cwd=str(REPO_ROOT), capture_output=True, text=True)
        # script should exit cleanly (we implemented early exit) and NOT create model
        assert res.returncode == 0
        assert not MODEL_PATH.exists(), "Model should NOT be created when samples < 72"

    finally:
        _restore(MODEL_PATH)
        _restore(MERGED_PATH)
