from pathlib import Path

import pytest

BATS = sorted(Path(__file__).resolve().parents[1].glob("*.bat"))


@pytest.mark.parametrize("bat", BATS, ids=lambda p: p.name)
def test_bat_is_ascii_crlf_without_bom(bat):
    raw = bat.read_bytes()
    # nie-ASCII (np. polskie litery) psuje parsowanie cmd przy chcp 65001
    assert all(b < 128 for b in raw), f"{bat.name}: znaki spoza ASCII"
    assert b"\n" not in raw.replace(b"\r\n", b""), f"{bat.name}: konce linii inne niz CRLF"
    assert b"\x07" not in raw, f"{bat.name}: znak BEL (pomylka \a w sciezce)"
