# -*- coding: utf-8 -*-
"""
build_presentation.py — buduje PDF prezentacji i plik z notatkami mowcy z docs/prezentacja/.

Zrodla: docs/prezentacja/slajdy/*.html (jeden slajd = jedna sekcja 1920x1080, style w tekscie),
docs/prezentacja/obrazy/*.png i docs/prezentacja/prezentacja.json (kolejnosc slajdow, czcionki).
Wyniki: docs/Prezentacja_SmogGuardAI.pdf i docs/Prezentacja_notatki.md.

PDF powstaje przez Microsoft Edge albo Google Chrome (tryb bez okna, drukowanie do PDF), wiec nic
nie trzeba instalowac. Czcionki (Rubik, Nunito Sans) pobiera z Google Fonts, wiec potrzebny jest internet;
bez niego przegladarka uzyje czcionek zastepczych.

Uzycie:
    py src/build_presentation.py              # PDF + notatki
    py src/build_presentation.py --html-only  # tylko docs/prezentacja/prezentacja.html (podglad w przegladarce)
Edycja: zmien tekst w docs/prezentacja/slajdy/<slajd>.html i uruchom ponownie.
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
PRES = BASE / "docs" / "prezentacja"
OUT_PDF = BASE / "docs" / "Prezentacja_SmogGuardAI.pdf"
OUT_NOTES = BASE / "docs" / "Prezentacja_notatki.md"
OUT_HTML = PRES / "prezentacja.html"

CSS = """
@page { size: 1920px 1080px; margin: 0 }
* { box-sizing: border-box }
html, body { margin: 0; padding: 0; background: #FFFFFF; -webkit-print-color-adjust: exact; print-color-adjust: exact }
h1, h2, h3, p, ul, ol { margin: 0 }
section { position: relative; width: 1920px; height: 1080px; overflow: hidden; page-break-after: always; break-after: page }
table { width: 100%; border-collapse: collapse }
th, td { padding: 18px 20px; vertical-align: top; text-align: left }
th { font-weight: 700; border-bottom: 3px solid #14213D }
td { border-bottom: 1px solid #C9CDC4 }
b { font-weight: 700 }
"""

ICONS = {
    "Check": '<polyline points="20 6 9 17 4 12"></polyline>',
    "Warning": '<path d="M12 3 L22 20 L2 20 Z"></path><line x1="12" y1="10" x2="12" y2="14"></line><line x1="12" y1="17" x2="12" y2="17.5"></line>',
}


def _icon(match) -> str:
    name, style = match.group(1), match.group(2)
    color = (re.search(r"color:\s*([^;]+)", style) or [None, "#000"])[1].strip()
    size = "".join(re.findall(r"(?:width|height):[^;]+;?", style))
    body = ICONS.get(name, "")
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" '
            f'stroke-linejoin="round" style="{size};flex:none">{body}</svg>')


def convert_slide(src: str) -> str:
    """Slajd w formacie edytora (znaczniki x-shape, x-icon, aside) -> zwykly HTML."""
    s = re.sub(r"<aside>.*?</aside>", "", src, flags=re.S)
    s = re.sub(r'<x-shape kind="ellipse" style="([^"]*)"></x-shape>',
               lambda m: f'<div style="{m.group(1)};border-radius:50%"></div>', s)
    s = re.sub(r'<x-icon name="([A-Za-z]+)" style="([^"]*)"></x-icon>', _icon, s)
    return s


def notes_of(src: str) -> str:
    m = re.search(r"<aside>(.*?)</aside>", src, flags=re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def title_of(src: str) -> str:
    m = re.search(r"<h[12][^>]*>(.*?)</h[12]>", src, flags=re.S)
    return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""


def load_index() -> dict:
    return json.loads((PRES / "prezentacja.json").read_text(encoding="utf-8"))


def build_html(index: dict) -> str:
    sections = []
    for sid in index["kolejnosc"]:
        sections.append(convert_slide((PRES / "slajdy" / f"{sid}.html").read_text(encoding="utf-8")))
    return ("<!doctype html>\n<html lang=\"pl\"><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(index['tytul'])}</title>"
            f"<link rel=\"stylesheet\" href=\"{index['czcionki']}\">"
            f"<style>{CSS}</style></head><body>\n" + "\n".join(sections) + "\n</body></html>\n")


def build_notes(index: dict) -> str:
    out = [f"# {index['tytul']} — notatki mówcy", "",
           "Notatki do kolejnych slajdów (czas w nawiasach to propozycja). Plik jest generowany przez",
           "`src/build_presentation.py` z `docs/prezentacja/slajdy/`; edytuj slajdy, nie ten plik.", ""]
    for i, sid in enumerate(index["kolejnosc"], 1):
        src = (PRES / "slajdy" / f"{sid}.html").read_text(encoding="utf-8")
        out += [f"## Slajd {i}: {title_of(src)}", "", notes_of(src) or "(brak notatek)", ""]
    return "\n".join(out)


def find_browser():
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("chromium")


def render_pdf(html_path: Path, pdf_path: Path) -> None:
    browser = find_browser()
    if not browser:
        raise SystemExit("[ERR] Nie znaleziono Edge ani Chrome — zainstaluj przegladarke albo uzyj --html-only.")
    with tempfile.TemporaryDirectory() as prof:
        cmd = [browser, "--headless=new", "--disable-gpu", f"--user-data-dir={prof}", "--no-pdf-header-footer",
               "--virtual-time-budget=20000", f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()]
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    if not pdf_path.exists() or pdf_path.stat().st_size < 10_000:
        raise SystemExit("[ERR] Nie udalo sie wygenerowac PDF.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Buduje PDF prezentacji i notatki mowcy")
    ap.add_argument("--html-only", action="store_true", help="tylko prezentacja.html (bez PDF)")
    args = ap.parse_args()
    index = load_index()
    OUT_HTML.write_text(build_html(index), encoding="utf-8")
    OUT_NOTES.write_text(build_notes(index), encoding="utf-8")
    print(f"[OK] {OUT_HTML.relative_to(BASE)} i {OUT_NOTES.relative_to(BASE)}")
    if args.html_only:
        return
    render_pdf(OUT_HTML, OUT_PDF)
    print(f"[OK] {OUT_PDF.relative_to(BASE)} ({OUT_PDF.stat().st_size // 1024} KB, {len(index['kolejnosc'])} slajdow)")


if __name__ == "__main__":
    sys.exit(main())
