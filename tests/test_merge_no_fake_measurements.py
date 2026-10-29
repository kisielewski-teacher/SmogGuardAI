import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]


def test_hours_after_last_measurement_are_forecast_not_fake_measurements(tmp_path):
    idx = pd.date_range("2026-01-01", periods=48, freq="h")
    pd.DataFrame({"timestamp": idx, "y_true": 10.0 + np.arange(48) % 5, "y_pred": 11.0}).to_csv(tmp_path / "bt.csv", index=False)
    fut = pd.date_range(idx[-1] + pd.Timedelta(hours=1), periods=24, freq="h")
    pd.DataFrame({"timestamp": fut, "pm10_pred": 20.0, "pm10_pred_low": 15.0, "pm10_pred_high": 30.0}).to_csv(tmp_path / "pred.csv", index=False)
    pd.DataFrame({"timestamp": idx, "temperatura": 5.0, "predkosc_wiatru": 3.0}).to_csv(tmp_path / "weather.csv", index=False)
    out = tmp_path / "all.csv"
    r = subprocess.run([sys.executable, str(REPO / "src" / "merge_pm10_results.py"), "--pollutant", "pm10",
                        "--backtest", str(tmp_path / "bt.csv"), "--prediction", str(tmp_path / "pred.csv"),
                        "--weather", str(tmp_path / "weather.csv"), "--time-col", "timestamp", "--coalesce-hist",
                        "--out", str(out)], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    d = pd.read_csv(out, parse_dates=["timestamp"])
    future = d[d["timestamp"] > idx[-1]]
    assert len(future) == 24
    assert future["pm10_true"].isna().all(), "godziny po ostatnim pomiarze nie moga miec pomiaru"
    assert future["pm10_pred"].notna().all()
    assert (future["pm10_pred_low"] == 15.0).all() and (future["pm10_pred_high"] == 30.0).all()   # przedzial przechodzi
    if "temp" in d.columns:
        assert future["temp"].iloc[1:].isna().all()   # pogoda tez nie jest doklejana w przyszlosc (pierwsza godzina moze byc dopasowana w granicach 1 h)
    gap_idx = pd.date_range("2026-02-01", periods=10, freq="h")
    bt = pd.DataFrame({"timestamp": gap_idx, "y_true": [1.0, 2.0, np.nan, np.nan, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], "y_pred": 1.0})
    bt.to_csv(tmp_path / "bt2.csv", index=False)
    pd.DataFrame({"timestamp": gap_idx[-1:] + pd.Timedelta(hours=1), "pm10_pred": 3.0}).to_csv(tmp_path / "pred2.csv", index=False)
    pd.DataFrame({"timestamp": gap_idx, "temperatura": 5.0}).to_csv(tmp_path / "w2.csv", index=False)
    out2 = tmp_path / "all2.csv"
    r2 = subprocess.run([sys.executable, str(REPO / "src" / "merge_pm10_results.py"), "--pollutant", "pm10",
                         "--backtest", str(tmp_path / "bt2.csv"), "--prediction", str(tmp_path / "pred2.csv"),
                         "--weather", str(tmp_path / "w2.csv"), "--time-col", "timestamp", "--coalesce-hist",
                         "--out", str(out2)], cwd=str(REPO), capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr + r2.stdout
    d2 = pd.read_csv(out2, parse_dates=["timestamp"]).set_index("timestamp")
    assert np.isclose(d2.loc["2026-02-01 02:00", "pm10_true"], 3.0)      # luka MIEDZY pomiarami nadal interpolowana
