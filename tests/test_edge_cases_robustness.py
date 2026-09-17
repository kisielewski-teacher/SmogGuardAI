"""
Testy odpornościowe / symulacje skrajnych przypadków dla całego pipeline'u.
Cel: sprawdzić, że skrypty nie wywalają się z nieczytelnym tracebackiem na
danych, jakie realnie mogą się zdarzyć w produkcji (braki, duplikaty,
niekompletne pliki, ekstremalne parametry) — a jeśli się wywalają, że robią
to w sposób kontrolowany (czytelny komunikat, kod wyjścia), a nie cicho psując
dane wyjściowe.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"


def make_synthetic_hourly_csv(path: Path, n=200, target_col="PM10", seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2026-01-01", periods=n, freq="h")
    hours = np.arange(n) % 24
    base = 15 + 8 * np.sin(2 * np.pi * hours / 24) + rng.normal(0, 1.5, n)
    base = np.clip(base, 0.5, None)
    df = pd.DataFrame({
        "timestamp": ts,
        target_col: base,
        "temperatura": 10 + rng.normal(0, 1, n),
        "wilgotnosc_wzgledna": 70 + rng.normal(0, 5, n),
        "predkosc_wiatru": np.abs(rng.normal(3, 1, n)),
        "cisnienie": 1013 + rng.normal(0, 3, n),
    })
    df.to_csv(path, index=False)
    return df


def _train_small_model(tmp_path, target="PM10", n=200) -> Path:
    csv_path = tmp_path / "merged.csv"
    make_synthetic_hourly_csv(csv_path, n=n, target_col=target)
    model_out = tmp_path / "model.pkl"
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", target, "--time-col", "timestamp",
        "--lags", "1", "3", "--rolling", "3", "--n-estimators", "15",
        "--model-out", str(model_out), "--no-save-reports",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, f"setup: train failed: {r.stderr}"
    return csv_path, model_out


# --------------------------------------------------------------------------
# train_pm10_rf.py — dane zdegenerowane
# --------------------------------------------------------------------------
def test_train_empty_csv_fails_cleanly(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("timestamp,PM10\n")  # nagłówek, zero wierszy
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", "PM10", "--time-col", "timestamp",
        "--model-out", str(tmp_path / "model.pkl"), "--no-save-reports",
    ], cwd=str(REPO), capture_output=True, text=True)
    # Nie wymagamy sukcesu (nie ma jak trenować na zerze danych), ale MUSI być
    # kontrolowane zakończenie, a nie surowy Python traceback bez obsługi.
    assert not (tmp_path / "model.pkl").exists()
    if r.returncode != 0:
        assert "Traceback" not in r.stdout, "Błąd powinien być przechwycony i czytelnie zakomunikowany"


def test_train_all_nan_target_fails_cleanly(tmp_path):
    csv_path = tmp_path / "allnan.csv"
    ts = pd.date_range("2026-01-01", periods=100, freq="h")
    pd.DataFrame({"timestamp": ts, "PM10": [np.nan] * 100}).to_csv(csv_path, index=False)
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", "PM10", "--time-col", "timestamp",
        "--model-out", str(tmp_path / "model.pkl"), "--no-save-reports",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert not (tmp_path / "model.pkl").exists(), "Nie może powstać model z samych NaN"


def test_train_duplicate_timestamps_does_not_crash(tmp_path):
    csv_path = tmp_path / "dupes.csv"
    ts = pd.date_range("2026-01-01", periods=100, freq="h")
    df = make_synthetic_hourly_csv(csv_path, n=100)
    df2 = pd.concat([df, df.iloc[:20]], ignore_index=True)  # zduplikuj pierwsze 20 wierszy
    df2.to_csv(csv_path, index=False)
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", "PM10", "--time-col", "timestamp",
        "--lags", "1", "3", "--rolling", "3", "--n-estimators", "10",
        "--model-out", str(tmp_path / "model.pkl"), "--no-save-reports",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, f"Duplikaty timestampów nie powinny wywalać treningu: {r.stderr}"


# --------------------------------------------------------------------------
# predict_pm10.py — ekstremalne/nietypowe parametry
# --------------------------------------------------------------------------
def test_predict_negative_horizon_handled_gracefully(tmp_path):
    csv_path, model_out = _train_small_model(tmp_path)
    pred_out = tmp_path / "pred.csv"
    r = subprocess.run([
        sys.executable, str(SRC / "predict_pm10.py"),
        "--features", str(csv_path), "--model", str(model_out),
        "--out", str(pred_out), "--horizon", "-5", "--time-col", "timestamp",
    ], cwd=str(REPO), capture_output=True, text=True)
    # Skrypt ma własny try/except w __main__, więc MUSI zwrócić 0 nawet przy złych parametrach.
    assert r.returncode == 0, f"predict_pm10.py powinien łapać własne wyjątki: {r.stderr}\n{r.stdout}"


def test_predict_missing_model_file_handled_gracefully(tmp_path):
    csv_path, _ = _train_small_model(tmp_path)
    pred_out = tmp_path / "pred.csv"
    r = subprocess.run([
        sys.executable, str(SRC / "predict_pm10.py"),
        "--features", str(csv_path), "--model", str(tmp_path / "nonexistent.pkl"),
        "--out", str(pred_out), "--horizon", "5", "--time-col", "timestamp",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, "Brak modelu musi być obsłużony łagodnie (bez crasha pipeline'u)"
    assert not pred_out.exists()


def test_predict_zero_horizon_only_historical(tmp_path):
    csv_path, model_out = _train_small_model(tmp_path)
    pred_out = tmp_path / "pred.csv"
    r = subprocess.run([
        sys.executable, str(SRC / "predict_pm10.py"),
        "--features", str(csv_path), "--model", str(model_out),
        "--out", str(pred_out), "--horizon", "0", "--time-col", "timestamp",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert pred_out.exists()
    df = pd.read_csv(pred_out)
    assert len(df) > 0


def test_predict_huge_horizon_does_not_hang_or_crash(tmp_path):
    """Horyzont dużo większy niż typowe 72h — nie powinien się wywalić
    (choć oczywiście dokładność praktycznie zerowa dla tak długiego zakresu)."""
    csv_path, model_out = _train_small_model(tmp_path, n=200)
    pred_out = tmp_path / "pred.csv"
    r = subprocess.run([
        sys.executable, str(SRC / "predict_pm10.py"),
        "--features", str(csv_path), "--model", str(model_out),
        "--out", str(pred_out), "--horizon", "500", "--time-col", "timestamp",
    ], cwd=str(REPO), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"{r.stderr}\n{r.stdout}"
    assert pred_out.exists()


# --------------------------------------------------------------------------
# backtest_horizon.py — horyzont większy niż dostępna historia
# --------------------------------------------------------------------------
def test_backtest_horizon_too_large_for_data_fails_cleanly(tmp_path):
    csv_path, model_out = _train_small_model(tmp_path, n=100)
    out_csv = tmp_path / "acc.csv"
    r = subprocess.run([
        sys.executable, str(SRC / "backtest_horizon.py"),
        "--csv-path", str(csv_path), "--model", str(model_out), "--target", "PM10",
        "--max-horizon", "500", "--step-hours", "24", "--out", str(out_csv),
    ], cwd=str(REPO), capture_output=True, text=True)
    # Za mało danych na horyzont 500h przy 100 wierszach -> brak origins.
    # Wymagamy czytelnego zakończenia (kontrolowany exit 1 + komunikat), nie surowego tracebacku.
    if r.returncode != 0:
        assert "Traceback" not in r.stdout
        assert ("Brak wynik" in r.stdout) or ("Brak wynik" in r.stderr)


# --------------------------------------------------------------------------
# merge_pm10_results.py — brak wspólnych timestampów
# --------------------------------------------------------------------------
def test_merge_pm10_results_no_overlapping_timestamps(tmp_path):
    back = tmp_path / "backtest.csv"
    pred = tmp_path / "pred.csv"
    weather = tmp_path / "weather.csv"
    out = tmp_path / "all_latest.csv"

    pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=5, freq="h"),
        "y_true": [1.0, 2.0, 3.0, 4.0, 5.0],
        "y_pred": [1.1, 2.1, 2.9, 4.2, 4.8],
    }).to_csv(back, index=False)

    # predykcja w zupełnie innym zakresie czasu (brak nakładania)
    pd.DataFrame({
        "timestamp": pd.date_range("2030-01-01", periods=3, freq="h"),
        "pm10_pred": [5.5, 6.0, 6.5],
    }).to_csv(pred, index=False)

    pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=5, freq="h"),
        "temperatura": np.linspace(0, 4, 5),
    }).to_csv(weather, index=False)

    r = subprocess.run([
        sys.executable, str(SRC / "merge_pm10_results.py"),
        "--pollutant", "pm10",
        "--backtest", str(back), "--prediction", str(pred), "--weather", str(weather),
        "--time-col", "timestamp", "--coalesce-hist", "--out", str(out),
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, f"Brak nakładających się timestampów nie powinien wywalać scalania: {r.stderr}\n{r.stdout}"
    assert out.exists()


def test_merge_pm10_results_missing_files_fails_cleanly(tmp_path):
    r = subprocess.run([
        sys.executable, str(SRC / "merge_pm10_results.py"),
        "--pollutant", "pm10",
        "--backtest", str(tmp_path / "nope1.csv"),
        "--prediction", str(tmp_path / "nope2.csv"),
        "--weather", str(tmp_path / "nope3.csv"),
        "--time-col", "timestamp", "--out", str(tmp_path / "out.csv"),
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode != 0
    assert "Traceback" not in r.stdout or "FileNotFoundError" in r.stdout + r.stderr


# --------------------------------------------------------------------------
# resolve_best_target_alias — przypadki brzegowe
# --------------------------------------------------------------------------
def test_resolve_best_target_alias_empty_dataframe():
    sys.path.insert(0, str(SRC))
    import importlib
    if "utils_features" in sys.modules:
        importlib.reload(sys.modules["utils_features"])
    import utils_features as uf

    df = pd.DataFrame(columns=["timestamp", "PM10"])
    best_alias, best_count = uf.resolve_best_target_alias(df, "PM10")
    assert best_alias is None
    assert best_count == 0


def test_resolve_best_target_alias_target_missing_entirely():
    sys.path.insert(0, str(SRC))
    import utils_features as uf

    df = pd.DataFrame({"foo": [1, 2, 3]})
    best_alias, best_count = uf.resolve_best_target_alias(df, "PM10")
    assert best_alias is None
    assert best_count == 0
