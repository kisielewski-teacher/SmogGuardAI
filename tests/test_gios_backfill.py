import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import gios_backfill as gb  # noqa: E402


class _Resp:
    def __init__(self, j): self._j = j
    def raise_for_status(self): pass
    def json(self): return self._j


def test_fetch_pages_and_drops_nulls(monkeypatch):
    pages = {
        0: {"totalPages": 2, "Lista": [{"Data": "2026-10-30 00:00:00", "Wartość": 10.0},
                                       {"Data": "2026-10-30 01:00:00", "Wartość": None}]},
        1: {"totalPages": 2, "Lista": [{"Data": "2026-10-30 02:00:00", "Wartość": 12.5}]},
    }
    monkeypatch.setattr(gb.requests, "get", lambda url, timeout, params: _Resp(pages[params["page"]]))
    df = gb.fetch_pm10("2026-10-30", "2026-10-30")
    assert list(df["PM10"]) == [10.0, 12.5]


def test_main_replaces_overlap_without_duplicates(monkeypatch, tmp_path):
    out = tmp_path / "g.csv"
    pd.DataFrame({"timestamp": ["2026-10-29 22:00:00", "2026-11-25 08:00:00"], "station": ["s", "s"],
                  "PM2.5": [None, None], "PM10": [18.4, 99.0], "NO2": [None, None], "O3": [None, None]}
                 ).to_csv(out, index=False)
    monkeypatch.setattr(gb, "OUT", out)
    monkeypatch.setattr(gb, "fetch_pm10", lambda a, b: pd.DataFrame(
        {"timestamp": pd.to_datetime(["2026-10-30 00:00:00", "2026-11-25 07:00:00"]), "PM10": [14.9, 7.9]}))
    monkeypatch.setattr(sys, "argv", ["x", "--from", "2026-10-30"])
    assert gb.main() == 0
    r = pd.read_csv(out, parse_dates=["timestamp"])
    assert r["timestamp"].is_unique and r["timestamp"].is_monotonic_increasing
    assert list(r["PM10"]) == [18.4, 14.9, 7.9]  # wpis z 25.11 08:00 (99.0) usuniety
