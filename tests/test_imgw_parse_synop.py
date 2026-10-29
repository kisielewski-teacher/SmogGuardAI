import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import imgw_historical_backfill as m  # noqa: E402


def _row(post, **kw):
    base = {c: None for c in m.COLUMNS}
    base.update(POST=post, ROK=2024, MC=1, DZ=1, GG=0, TEMP=7.6, FWR=3.1, WLGW=94, WO6G=0.2, PPPM=1005.0)
    base.update(kw)
    return base


def test_parse_handles_space_padded_station_names():
    # w archiwum 2024 nazwy stacji sa dopelnione spacjami
    df = pd.DataFrame([_row("KOSZALIN                      "), _row("USTKA   "), _row("WARSZAWA")])
    out = m._parse_synop(df)
    assert sorted(out["stacja"]) == ["Koszalin", "Ustka"]
    assert out["temperatura"].iloc[0] == 7.6
    assert out["timestamp"].iloc[0] == pd.Timestamp("2024-01-01 00:00")


def test_parse_empty_and_unknown_stations():
    df = pd.DataFrame([_row("WARSZAWA")])
    assert m._parse_synop(df).empty
