from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app" / "app_extended_multi.py"


@pytest.mark.skipif(not (APP.parent.parent / "data" / "merged_hourly.csv").exists(), reason="brak danych do panelu")
def test_panel_renders_without_exceptions_and_has_wind_rose_tab():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=180)
    at.run()
    assert not at.exception, [str(e.value)[:200] for e in at.exception]
    labels = [t.label for t in at.tabs]
    assert "Róża wiatrów" in labels
    assert "Dokładność prognozy" in labels
    texts = " ".join([c.value for c in at.caption] + [m.value for m in at.markdown])
    assert "Open-Meteo" not in texts            # nie uzywamy juz Open-Meteo (licencja niekomercyjna)
