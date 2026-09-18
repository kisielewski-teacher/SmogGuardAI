import importlib.util
import sys
import os
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
DATA = REPO / "data"


class DummyResp:
    def __init__(self, json_data=None, text_data=None, status=200):
        self._json = json_data
        self.text = text_data or ("" if json_data is None else str(json_data))
        self.status_code = status

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_waqi_fetch_mocked(monkeypatch, tmp_path):
    # ensure WAQI_TOKEN present before import (module checks at import time)
    monkeypatch.setenv("WAQI_TOKEN", "test-token")

    mod = load_module_from_path("waqi_fetch_test", SRC / "waqi_fetch.py")

    sample = {
        "status": "ok",
        "data": {
            "time": {"s": "2026-01-01 00:00:00"},
            "aqi": 12,
            "iaqi": {"pm25": {"v": 5.1}, "pm10": {"v": 7.2}}
        }
    }

    # patch session.get used inside module
    monkeypatch.setattr(mod, "session", type("S", (), {"get": lambda *a, **k: DummyResp(json_data=sample)})())

    data = mod.fetch()
    assert data["aqi"] == 12

    df = mod.parse_to_row(data)
    assert "PM2.5" in df.columns
    assert df["PM2.5"].iloc[0] == 5.1


def test_waqi_fetch_column_alignment_survives_field_reordering(monkeypatch, tmp_path):
    """Regresja dla realnego buga znalezionego w produkcji: WAQI API nie
    gwarantuje kolejności kluczy w 'iaqi' między wywołaniami. Stary kod
    dopisywał df.to_csv(..., header=False) pozycyjnie, więc gdy druga
    odpowiedź miała klucze w innej kolejności (np. brak 'w', inna kolejność
    'p'/'t'/'h'), wartości trafiały pod ZŁE nagłówki (np. ciśnienie pod PM10)
    bez żadnego błędu — zobacz historyczne dane: ~28 wierszy z ciśnieniem
    55-91 hPa i ujemną wilgotnością/wiatrem. Ten test gwarantuje, że kolumny
    są zawsze wyrównywane do nagłówka pliku przed zapisem."""
    monkeypatch.setenv("WAQI_TOKEN", "test-token")
    mod = load_module_from_path("waqi_fetch_align_test", SRC / "waqi_fetch.py")
    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUTPUT_FILE", "aqicn_test.csv")

    # Pierwsza odpowiedź: kolejność iaqi = h, p, t, w, pm10
    sample1 = {
        "status": "ok",
        "data": {
            "time": {"s": "2026-01-01 00:00:00"},
            "aqi": 20,
            "iaqi": {"h": {"v": 80}, "p": {"v": 1015}, "t": {"v": 5}, "w": {"v": 3}, "pm10": {"v": 12}},
        },
    }
    # Druga odpowiedź: INNA kolejność iaqi (pm10 pierwsze, brak 'w') — dokładnie
    # ten scenariusz, który wcześniej psuł wyrównanie kolumn.
    sample2 = {
        "status": "ok",
        "data": {
            "time": {"s": "2026-01-01 01:00:00"},
            "aqi": 18,
            "iaqi": {"pm10": {"v": 14}, "t": {"v": 6}, "h": {"v": 82}, "p": {"v": 1016}},
        },
    }

    responses = [sample1, sample2]

    def fake_get(*a, **k):
        return DummyResp(json_data=responses.pop(0))

    monkeypatch.setattr(mod, "session", type("S", (), {"get": staticmethod(fake_get)})())

    mod.main()
    mod.main()

    out = pd.read_csv(tmp_path / "aqicn_test.csv")
    assert list(out.columns) == ["timestamp", "aqi", "wilgotnosc_wzgledna", "cisnienie", "PM10", "temperatura", "predkosc_wiatru", "wg", "_backfilled"]
    assert len(out) == 2
    # Wiersz 2 (kolejność iaqi odwrócona) MUSI mieć wartości pod właściwymi kolumnami,
    # nie przesunięte pozycyjnie.
    row2 = out.iloc[1]
    assert row2["PM10"] == 14
    assert row2["temperatura"] == 6
    assert row2["wilgotnosc_wzgledna"] == 82
    assert row2["cisnienie"] == 1016
    assert 800 <= row2["cisnienie"] <= 1100, "Ciśnienie nie może wylądować w innej kolumnie"


def test_syngeos_fetch_main_mocked(monkeypatch, tmp_path):
    mod = load_module_from_path("syngeos_fetch_test", SRC / "syngeos_fetch.py")

    # sample HTML widget that contains PM2.5 in parentheses and label
    html = '<div class="widget-body"><p class="widget-body__sensor">(3.5 µg/m³)</p><p class="widget-body__sensor">PM2.5</p></div>'

    monkeypatch.setattr(mod, "requests", type("R", (), {"get": lambda *a, **k: DummyResp(text_data=html)}))

    out = tmp_path / "syngeos_all.csv"
    agg = tmp_path / "syngeos_agg.csv"
    # call main() by setting sys.argv
    monkeypatch.setattr(sys, "argv", ["syngeos_fetch.py", "--url", "http://example/", "--out", str(out), "--aggregate", str(agg), "--resample", "h"])

    mod.main()

    assert out.exists()
    assert agg.exists()
    df = pd.read_csv(agg)
    assert "pm25_mean" in df.columns


def test_imgw_fetch_mocked(monkeypatch, tmp_path):
    mod = load_module_from_path("imgw_fetch_test", SRC / "imgw_fetch.py")

    # sample IMGW JSON: list of stations with data_pomiaru/godzina_pomiaru
    sample = [
        {"stacja": "Słupsk, ul. Kniaziewicza", "data_pomiaru": "2026-01-01", "godzina_pomiaru": 0, "temperatura": 1.2, "predkosc_wiatru": 0.5, "wilgotnosc_wzgledna": 90, "cisnienie": 1012},
        {"stacja": "Ustka", "data_pomiaru": "2026-01-01", "godzina_pomiaru": 0, "temperatura": 0.5}
    ]

    monkeypatch.setattr(mod, "requests", type("R", (), {"get": lambda *a, **k: DummyResp(json_data=sample)}))

    out = tmp_path / "imgw_synop_hourly.csv"
    monkeypatch.setattr(sys, "argv", ["imgw_fetch.py", "--out", str(out)])
    mod.main()

    assert out.exists()
    df = pd.read_csv(out)
    assert "temperatura" in df.columns
    assert "stacja" in df.columns


def test_sensor_community_fetch_mocked(monkeypatch, tmp_path):
    mod = load_module_from_path("sensor_community_fetch_test", SRC / "sensor_community_fetch.py")

    # create a fake sensor entry with sensordatavalues containing PM2.5
    sensor = {
        "sensor": {"id": 123},
        "lastMeasurement": {"dateTime": "2026-01-01T00:00:00Z"},
        "sensordatavalues": [
            {"value_type": "P1", "value": "10"},
            {"value_type": "P2", "value": "5.5"}
        ]
    }

    monkeypatch.setattr(mod, "_query_radius", lambda r: [sensor])

    out = tmp_path / "sensor_community_slupsk.csv"
    monkeypatch.setattr(mod, "OUT", out)

    # call main; it should write the file
    mod.main()

    assert out.exists()
    df = pd.read_csv(out)
    assert "PM2.5" in df.columns
    assert df["PM2.5"].iloc[0] == 5.5
