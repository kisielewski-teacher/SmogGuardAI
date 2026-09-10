import importlib.util
import sys
from pathlib import Path
import json

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"


def load_mod(path):
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_syngeos_parse_nested_json():
    mod = load_mod(SRC / "syngeos_fetch.py")
    payload = {"wrapper": {"metrics": {"pm2_5": 3.14, "pm10": 6}}}
    s = json.dumps(payload)
    out = mod.parse_response_text(s)
    assert out["pm2_5"] == 3.14


def test_syngeos_html_label_after_value_variant():
    mod = load_mod(SRC / "syngeos_fetch.py")
    html = '<div class="widget-body"><p class="widget-body__sensor">(4.2 µg/m³)</p><p class="widget-body__sensor">PM2.5</p></div>'
    out = mod.parse_response_text(html)
    assert out["pm2_5"] == 4.2


def test_syngeos_reject_unrealistic_values():
    mod = load_mod(SRC / "syngeos_fetch.py")
    # value that looks like a year should be rejected (>1000)
    html = '(2026 µg/m³) PM2.5'
    out = mod.parse_response_text(html)
    assert out["pm2_5"] is None


def test_waqi_parse_pm2_5_alias_and_tz(monkeypatch):
    # ensure WAQI_TOKEN present for safe import
    monkeypatch.setenv("WAQI_TOKEN", "x")
    mod = load_mod(SRC / "waqi_fetch.py")

    sample = {
        "time": {"s": "2026-01-01 01:00:00+01:00"},
        "aqi": 10,
        "iaqi": {"pm2_5": {"v": 2.5}, "pm10": {"v": 7}}
    }
    df = mod.parse_to_row(sample)
    # alias pm2_5 should map to PM2.5 because we added mapping
    assert "PM2.5" in df.columns
    assert df["PM2.5"].iloc[0] == 2.5
    # timestamp parsed (tz-aware string should parse without error)
    assert pd.to_datetime(df["timestamp"].iloc[0]).hour in (1,)


def test_imgw_normalize_missing_hour_and_filter():
    mod = load_mod(SRC / "imgw_fetch.py")
    sample = [
        {"stacja": "Słupsk, ul. Kniaziewicza", "data_pomiaru": "2026-01-01", "godzina_pomiaru": 0, "temperatura": 1.2},
        {"stacja": "Ustka", "data_pomiaru": "2026-01-01", "godzina_pomiaru": None, "temperatura": 0.5},
    ]
    df = pd.DataFrame(sample)
    normalized = mod.normalize(df, stations_filter=["Kniaziewicza"])
    # first row should match filter and have valid timestamp
    assert not normalized.empty
    assert normalized.iloc[0]["stacja"].startswith("Słupsk")
    assert pd.notnull(normalized.iloc[0]["timestamp"])


def test_sensor_community_handles_comma_decimal(monkeypatch, tmp_path):
    mod = load_mod(SRC / "sensor_community_fetch.py")

    sensor = {
        "sensor": {"id": 999},
        "lastMeasurement": {"dateTime": "2026-01-01T00:00:00Z"},
        "sensordatavalues": [
            {"value_type": "P1", "value": "10"},
            {"value_type": "P2", "value": "5,5"}  # comma decimal — should be handled gracefully
        ]
    }

    monkeypatch.setattr(mod, "_query_radius", lambda r: [sensor])
    # write OUT to tmp path
    monkeypatch.setenv("LAT", "54.4639")
    monkeypatch.setenv("LON", "17.0287")
    monkeypatch.setattr(mod, "OUT", tmp_path / "sensor_community_slupsk.csv")

    # should not raise and should either skip or write only numeric values (P1 exists)
    mod.main()
    out = tmp_path / "sensor_community_slupsk.csv"
    # current behaviour: when PM2.5 is not parseable the script skips writing — ensure no exception and no file
    assert not out.exists()
