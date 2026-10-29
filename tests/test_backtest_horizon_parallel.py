import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from test_edge_cases_robustness import _train_small_model

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"


def _run(csv_path, model_out, out_csv, jobs):
    r = subprocess.run([
        sys.executable, str(SRC / "backtest_horizon.py"),
        "--csv-path", str(csv_path), "--model", str(model_out), "--target", "PM10",
        "--max-horizon", "6", "--step-hours", "12", "--jobs", str(jobs), "--out", str(out_csv),
    ], cwd=str(REPO), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"{r.stderr}\n{r.stdout}"
    return pd.read_csv(out_csv)


def test_parallel_horizon_audit_matches_single_process(tmp_path):
    csv_path, model_out = _train_small_model(tmp_path, n=200)
    one = _run(csv_path, model_out, tmp_path / "one.csv", 1)
    two = _run(csv_path, model_out, tmp_path / "two.csv", 2)
    assert one.shape == two.shape and len(one) == 6
    assert np.allclose(one.values, two.values, equal_nan=True)
