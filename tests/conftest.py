import os

import pytest

# Testy, ktore podmieniaja prawdziwe pliki projektu (data/, models/, outputs/).
# - Uruchomione przez run_tests.bat (tymczasowa kopia, SMOG_TESTS_ISOLATED=1) biegna normalnie,
#   ale w OSOBNEJ fazie, po kolei (marker real_files), zeby nie scigac sie z innymi testami.
# - Uruchomione "gola" komenda `pytest tests` sa POMIJANE, zeby nie uszkodzic prawdziwych danych.
REAL_FILE_TESTS = {
    "test_bugfixes.py",
    "test_fetchers_mocked.py",
    "test_pipeline_integration.py",
    "test_predict_pm25_fallback.py",
    "test_train_pm25_min_rows.py",
}
ISOLATED = os.environ.get("SMOG_TESTS_ISOLATED") == "1"


def pytest_configure(config):
    config.addinivalue_line("markers", "real_files: test podmienia pliki projektu (data/models/outputs) - biegnie sam, bez rownoleglosci")


def pytest_collection_modifyitems(config, items):
    skip = pytest.mark.skip(reason="rusza prawdziwe data/models/outputs - uruchom run_tests.bat (kopia projektu)")
    for item in items:
        if item.path.name in REAL_FILE_TESTS:
            if ISOLATED:
                item.add_marker(pytest.mark.real_files)
            else:
                item.add_marker(skip)
