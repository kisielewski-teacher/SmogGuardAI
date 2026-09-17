"""
Regresja dla optymalizacji rozmiaru modelu (sesja: "zajmij się rozmiarem modeli
bez straty jakości"):
- domyślne min_samples_leaf=10 (zamiast sklearn-owego 1) — mniejsze drzewa,
  mniejszy plik, w praktyce RÓWNIEŻ lepsze MAE/R^2 na danych PM10 (bo liście
  z 1 próbką to przeuczenie szumu, nie sygnał),
- joblib.dump z compress=6 — bezstratna kompresja pliku modelu.
"""
import subprocess
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"


def make_synthetic_hourly_csv(path: Path, n=300, target_col="PM10", seed=0) -> pd.DataFrame:
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


def _load_pipeline(path: Path):
    sys.path.insert(0, str(SRC))
    from train_pm10_rf import ExtendedFeatureBuilder, FeatureConfig
    sys.modules["__main__"].ExtendedFeatureBuilder = ExtendedFeatureBuilder
    sys.modules["__main__"].FeatureConfig = FeatureConfig
    return joblib.load(path)


def test_default_min_samples_leaf_is_10(tmp_path):
    csv_path = tmp_path / "merged.csv"
    make_synthetic_hourly_csv(csv_path, n=300)
    model_out = tmp_path / "model.pkl"
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", "PM10", "--time-col", "timestamp",
        "--lags", "1", "3", "--rolling", "3", "--n-estimators", "20",
        "--model-out", str(model_out), "--no-save-reports",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    pipe = _load_pipeline(model_out)
    rf = pipe.named_steps["model"]
    assert rf.min_samples_leaf == 10, "Domyślne min_samples_leaf musi wynosić 10, nie sklearnowe 1"


def test_min_samples_leaf_cli_override_respected(tmp_path):
    csv_path = tmp_path / "merged.csv"
    make_synthetic_hourly_csv(csv_path, n=300)
    model_out = tmp_path / "model.pkl"
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", "PM10", "--time-col", "timestamp",
        "--lags", "1", "3", "--rolling", "3", "--n-estimators", "20",
        "--min-samples-leaf", "3",
        "--model-out", str(model_out), "--no-save-reports",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    pipe = _load_pipeline(model_out)
    assert pipe.named_steps["model"].min_samples_leaf == 3


def test_saved_model_is_compressed_smaller_than_uncompressed(tmp_path):
    """Regresja: joblib.dump musi używać compress=, inaczej pliki wracają do
    dziesiątek/setek MB na realnych danych (patrz README — bez tego 1 model = ~130 MB)."""
    csv_path = tmp_path / "merged.csv"
    make_synthetic_hourly_csv(csv_path, n=400, seed=1)
    model_out = tmp_path / "model.pkl"
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", "PM10", "--time-col", "timestamp",
        "--lags", "1", "3", "6", "--rolling", "3", "6", "--n-estimators", "50",
        "--min-samples-leaf", "1",  # celowo bez regularyzacji, żeby drzewa były duże
        "--model-out", str(model_out), "--no-save-reports",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    pipe = _load_pipeline(model_out)
    uncompressed_path = tmp_path / "uncompressed.pkl"
    joblib.dump(pipe, uncompressed_path, compress=0)

    compressed_size = model_out.stat().st_size
    uncompressed_size = uncompressed_path.stat().st_size
    assert compressed_size < uncompressed_size, (
        f"Zapisany model ({compressed_size}B) powinien być mniejszy niż wersja "
        f"bez kompresji ({uncompressed_size}B) — sprawdź czy joblib.dump używa compress="
    )
