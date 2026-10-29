"""Uruchamia testy na tymczasowej KOPII projektu, rownolegle (pytest-xdist).

Czesc testow podmienia prawdziwe pliki (data/, models/, outputs/) — w kopii nie moze
to uszkodzic danych produkcyjnych ani kolidowac z pipeline'em. Uzycie:
    py tests/run_isolated.py [-n 6] [argumenty pytest...]
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
SKIP = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "logs")


def main(argv):
    workers = "6"
    if argv[:1] == ["-n"] and len(argv) >= 2:
        workers, argv = argv[1], argv[2:]
    tmp = Path(tempfile.mkdtemp(prefix="smogguard_tests_"))
    try:
        copy = tmp / "proj"
        shutil.copytree(PROJ, copy, ignore=SKIP)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "SMOG_TESTS_ISOLATED": "1"}
        base = [sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"]
        # Faza 1: testy bezpieczne - rownolegle. Faza 2: testy podmieniajace pliki - po kolei.
        rc1 = subprocess.call(base + ["-n", workers, "-m", "not real_files", *argv], cwd=str(copy), env=env)
        rc2 = subprocess.call(base + ["-m", "real_files", *argv], cwd=str(copy), env=env)
        return rc1 or rc2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
