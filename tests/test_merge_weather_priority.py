import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import merge_hourly as mh  # noqa: E402


def _frame(rows):
    return pd.DataFrame(rows, columns=["stacja", "timestamp", "temperatura", "cisnienie"]).assign(
        timestamp=lambda d: pd.to_datetime(d["timestamp"]))


def test_nearest_station_wins_regardless_of_row_order():
    rows = [("Chojnice", "2026-01-01 10:00", 1.0, 1000.0),
            ("Ustka", "2026-01-01 10:00", 5.0, 1010.0),
            ("Koszalin", "2026-01-01 10:00", 3.0, 1005.0)]
    for order in ([0, 1, 2], [2, 1, 0], [1, 0, 2]):
        out = mh.collapse_weather_stations(_frame([rows[k] for k in order]))
        assert len(out) == 1 and out["stacja"].iloc[0] == "Ustka"
        assert out["temperatura"].iloc[0] == 5.0


def test_missing_value_is_filled_from_next_station():
    rows = [("Ustka", "2026-01-01 10:00", 5.0, np.nan),
            ("Koszalin", "2026-01-01 10:00", 3.0, 1005.0),
            ("Chojnice", "2026-01-01 11:00", 2.0, 999.0)]
    out = mh.collapse_weather_stations(_frame(rows)).set_index("timestamp")
    first = out.loc[pd.Timestamp("2026-01-01 10:00")]
    assert first["temperatura"] == 5.0 and first["cisnienie"] == 1005.0   # cisnienie z Koszalina
    assert out.loc[pd.Timestamp("2026-01-01 11:00"), "stacja"] == "Chojnice"  # jedyna dostepna
