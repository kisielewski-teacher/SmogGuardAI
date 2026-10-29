import sys
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import gios_real_backfill as gb  # noqa: E402


def test_backfill_with_start_keeps_older_history(tmp_path, monkeypatch):
    path = tmp_path / "gios_slupsk.csv"
    old = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=48, freq="h"),
        "station": "S", "PM2.5": pd.NA, "PM10": 10.0, "NO2": pd.NA, "O3": pd.NA,
    })
    old.to_csv(path, index=False)

    now = pd.Timestamp.now().floor("h")
    start = now - pd.Timedelta(hours=5)

    def fake_history(sensor_id, date_from, date_to):
        ts = pd.date_range(date_from.floor("h"), now, freq="h")
        return pd.DataFrame({"timestamp": ts, "value": 99.0})

    monkeypatch.setattr(gb, "GIOS_PATH", path)
    monkeypatch.setattr(gb, "_discover_sensor_ids", lambda: ("S", {"PM10": 1}))
    monkeypatch.setattr(gb, "fetch_sensor_history", fake_history)
    monkeypatch.setattr(sys, "argv", ["gios_real_backfill.py", "--start", str(start.date())])
    gb.main()

    out = pd.read_csv(path, parse_dates=["timestamp"])
    assert out["timestamp"].min() == pd.Timestamp("2026-01-01")  # historia nie zniknela
    assert (out["timestamp"].is_monotonic_increasing) and out["timestamp"].is_unique
    assert out["PM10"].iloc[0] == 10.0
    assert out["PM10"].iloc[-1] == 99.0  # nowe pomiary dolaczone
