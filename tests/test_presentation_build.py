import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import build_presentation as bp  # noqa: E402


def test_slide_sources_convert_to_plain_html_and_images_exist():
    index = bp.load_index()
    assert len(index["kolejnosc"]) == 10
    page = bp.build_html(index)
    assert page.count("<section ") == 10
    for leftover in ("<x-shape", "<x-icon", "<aside", "/_blob/"):
        assert leftover not in page, leftover
    assert "<svg" in page                                  # ikony zamienione na SVG
    for sid in index["kolejnosc"]:
        src = (bp.PRES / "slajdy" / f"{sid}.html").read_text(encoding="utf-8")
        assert f'<section id="{sid}"' in src
        for img in __import__("re").findall(r'src="(obrazy/[^"]+)"', src):
            assert (bp.PRES / img).exists(), img


def test_speaker_notes_exist_for_every_slide():
    index = bp.load_index()
    notes = bp.build_notes(index)
    assert notes.count("## Slajd ") == 10
    assert "(brak notatek)" not in notes
