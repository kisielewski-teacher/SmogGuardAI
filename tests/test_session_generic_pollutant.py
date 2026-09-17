"""
Testy regresyjne dla zmian z bieżącej sesji: uogólnienie pipeline'u PM10 na
dowolne zanieczyszczenie (PM10 i PM2.5 przez ten sam kod), tak żeby dodanie
PM2.5 (albo kolejnego zanieczyszczenia w przyszłości) nie psuło cichych założeń
w skryptach napisanych pierwotnie tylko dla PM10.

Sprawdzane bugi znalezione i naprawione w tej sesji:
1. `resolve_best_target_alias` myliła kolumny-metadane (pm25_count,
   PM2.5_is_estimated) z prawdziwymi danymi stężenia.
2. `train_pm10_rf.py` trenował na garstce wierszy zamiast na aliasie z
   większą liczbą realnych danych (< 10 -> teraz porównanie liczności).
3. `train_pm10_rf.py` nadpisywał raport ważności cech (`pm10_feature_importances.csv`)
   niezależnie od faktycznego targetu.
4. `predict_pm10.py` zawsze nazywał kolumnę wynikową 'pm10_pred', nawet dla PM2.5.
5. `backtest_pm10.py` zawsze zapisywał plik jako 'pm10_backtest_*.csv'.
6. `merge_pm10_results.py` nie miał trybu dla PM2.5 (flaga --pollutant).
7. `estimate_pm25_from_pm10.py`: gdy jest już >=72 realnych wierszy, ma
   "awansować" do czystych danych rzeczywistych zamiast dalej estymować.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"


def load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def make_synthetic_hourly_csv(path: Path, n=200, target_col="PM10", seed=0,
                               extra_cols: dict | None = None) -> pd.DataFrame:
    """Generuje syntetyczny, ale realistyczny szereg godzinowy (dobowa sinusoida +
    szum) — wystarczający do wytrenowania modelu (lags/rolling do 24h)."""
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2026-01-01", periods=n, freq="h")
    hours = np.arange(n) % 24
    base = 15 + 8 * np.sin(2 * np.pi * hours / 24) + rng.normal(0, 1.5, n)
    base = np.clip(base, 0.5, None)
    df = pd.DataFrame({
        "timestamp": ts,
        target_col: base,
        "temperatura": 10 + 5 * np.sin(2 * np.pi * hours / 24) + rng.normal(0, 1, n),
        "wilgotnosc_wzgledna": 70 + rng.normal(0, 5, n),
        "predkosc_wiatru": np.abs(rng.normal(3, 1, n)),
        "cisnienie": 1013 + rng.normal(0, 3, n),
    })
    if extra_cols:
        for k, v in extra_cols.items():
            df[k] = v
    df.to_csv(path, index=False)
    return df


# --------------------------------------------------------------------------
# 1) resolve_best_target_alias: musi ignorować kolumny-metadane.
# --------------------------------------------------------------------------
def test_resolve_best_target_alias_excludes_metadata_columns():
    mod = load_module_from_path("utils_features_alias_test", SRC / "utils_features.py")

    df = pd.DataFrame({
        "PM2.5": [np.nan] * 10 + [5.0, 6.0],          # tylko 2 realne wartości
        "pm25_count": list(range(12)),                 # metadana (liczba pomiarów), NIE stężenie
        "PM2.5_is_estimated": [True] * 12,              # flaga bool — same wartości "1"
        "pm25_mean": [3.0] * 12,                        # prawdziwy alias z 12 wartościami
    })

    best_alias, best_count = mod.resolve_best_target_alias(df, "PM2.5", min_rows=5)
    assert best_alias == "pm25_mean", f"Powinien wybrać 'pm25_mean', nie metadane. Wybrał: {best_alias}"
    assert best_count == 12


def test_resolve_best_target_alias_keeps_current_when_best():
    mod = load_module_from_path("utils_features_alias_test2", SRC / "utils_features.py")
    df = pd.DataFrame({
        "PM10": list(range(20)),         # kolumna docelowa ma najwięcej danych
        "PM10_x": [np.nan] * 15 + [1, 2, 3, 4, 5],
    })
    best_alias, best_count = mod.resolve_best_target_alias(df, "PM10", min_rows=5)
    assert best_alias is None  # PM10 jest już najlepsza — nie ma potrzeby zmiany
    assert best_count == 20


def test_resolve_best_target_alias_respects_min_rows():
    mod = load_module_from_path("utils_features_alias_test3", SRC / "utils_features.py")
    df = pd.DataFrame({
        "PM10": [np.nan] * 20,
        "PM10_y": [np.nan] * 17 + [1, 2, 3],  # tylko 3 wartości — poniżej progu
    })
    best_alias, best_count = mod.resolve_best_target_alias(df, "PM10", min_rows=10)
    assert best_alias is None
    assert best_count == 0


# --------------------------------------------------------------------------
# 2) train_pm10_rf.py: alias-fallback po liczności, nie po sztywnym progu "<10".
# --------------------------------------------------------------------------
def test_train_pm10_rf_uses_richer_alias(tmp_path):
    csv_path = tmp_path / "merged.csv"
    df = make_synthetic_hourly_csv(csv_path, n=200, target_col="PM10_y")
    # 'PM10' istnieje ale ma tylko kilkanaście wartości (> starego progu 10, ale << PM10_y)
    df["PM10"] = np.nan
    df.loc[df.index[:14], "PM10"] = 5.0
    df.to_csv(csv_path, index=False)

    model_out = tmp_path / "pm10_pipeline.pkl"
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", "PM10", "--time-col", "timestamp",
        "--lags", "1", "3", "--rolling", "3", "--n-estimators", "20",
        "--model-out", str(model_out), "--no-save-reports",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, f"train_pm10_rf.py failed: {r.stderr}\n{r.stdout}"
    assert "PM10_y" in r.stdout, "Powinien zgłosić użycie aliasu 'PM10_y' z większą liczbą danych"
    assert model_out.exists(), "Model powinien powstać (użyto danych z aliasu)"


def test_train_pm10_rf_skips_when_too_few_rows(tmp_path):
    csv_path = tmp_path / "merged.csv"
    ts = pd.date_range("2026-01-01", periods=20, freq="h")
    pd.DataFrame({"timestamp": ts, "PM2.5": np.linspace(1, 5, 20)}).to_csv(csv_path, index=False)

    model_out = tmp_path / "pm25_pipeline.pkl"
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", "PM2.5", "--time-col", "timestamp",
        "--lags", "1", "3", "--rolling", "3", "--n-estimators", "10",
        "--model-out", str(model_out), "--no-save-reports",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, f"skrypt powinien zakończyć się czysto: {r.stderr}\n{r.stdout}"
    assert not model_out.exists(), "Model NIE powinien powstać przy < 72 wierszach"
    assert "Pomijam trening" in r.stdout


def test_train_pm10_rf_report_filenames_match_target(tmp_path):
    """Regresja: raporty (feature_importances/trees) muszą być nazwane po
    modelu, inaczej trening PM2.5 nadpisuje raporty PM10 (ten sam plik)."""
    csv_path = tmp_path / "merged.csv"
    make_synthetic_hourly_csv(csv_path, n=150, target_col="PM10")

    model_out = tmp_path / "pm25_pipeline.pkl"
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", "PM10", "--time-col", "timestamp",
        "--lags", "1", "3", "--rolling", "3", "--n-estimators", "10",
        "--model-out", str(model_out),
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    assert (tmp_path / "pm25_feature_importances.csv").exists()
    assert (tmp_path / "pm25_trees.txt").exists()
    assert not (tmp_path / "pm10_feature_importances.csv").exists(), (
        "Nazwa raportu nie powinna być na sztywno 'pm10_*' — powinna pochodzić z --model-out"
    )


# --------------------------------------------------------------------------
# 3) predict_pm10.py: kolumna wynikowa nazwana zgodnie z targetem.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("target,expected_col", [("PM10", "pm10_pred"), ("PM2.5", "pm25_pred")])
def test_predict_pm10_output_column_matches_target(tmp_path, target, expected_col):
    csv_path = tmp_path / "merged.csv"
    make_synthetic_hourly_csv(csv_path, n=150, target_col=target)

    model_out = tmp_path / "model.pkl"
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", target, "--time-col", "timestamp",
        "--lags", "1", "3", "--rolling", "3", "--n-estimators", "15",
        "--model-out", str(model_out), "--no-save-reports",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert model_out.exists()

    pred_out = tmp_path / "pred.csv"
    r = subprocess.run([
        sys.executable, str(SRC / "predict_pm10.py"),
        "--features", str(csv_path), "--model", str(model_out),
        "--out", str(pred_out), "--horizon", "0", "--time-col", "timestamp",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, f"predict_pm10.py failed: {r.stderr}\n{r.stdout}"
    assert pred_out.exists()

    out = pd.read_csv(pred_out)
    assert expected_col in out.columns, f"Brak oczekiwanej kolumny '{expected_col}': {out.columns.tolist()}"
    assert out[expected_col].notna().any()


# --------------------------------------------------------------------------
# 4) backtest_pm10.py: nazwa pliku wynikowego zgodna z targetem.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("target,expected_prefix", [("PM10", "pm10_backtest_"), ("PM2.5", "pm25_backtest_")])
def test_backtest_pm10_output_filename_matches_target(tmp_path, target, expected_prefix):
    csv_path = tmp_path / "merged.csv"
    make_synthetic_hourly_csv(csv_path, n=150, target_col=target)

    model_out = tmp_path / "model.pkl"
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", target, "--time-col", "timestamp",
        "--lags", "1", "3", "--rolling", "3", "--n-estimators", "15",
        "--model-out", str(model_out), "--no-save-reports",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    out_dir = tmp_path / "outputs"
    r = subprocess.run([
        sys.executable, str(SRC / "backtest_pm10.py"),
        "--csv-path", str(csv_path), "--target", target, "--model", str(model_out),
        "--out-dir", str(out_dir),
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, f"backtest_pm10.py failed: {r.stderr}\n{r.stdout}"

    matches = list(out_dir.glob(f"{expected_prefix}*.csv"))
    assert matches, f"Brak pliku zaczynającego się od '{expected_prefix}' w {list(out_dir.iterdir())}"
    wrong_prefix = "pm25_backtest_" if expected_prefix == "pm10_backtest_" else "pm10_backtest_"
    assert not list(out_dir.glob(f"{wrong_prefix}*.csv")), "Plik nie powinien mieć nazwy innego zanieczyszczenia"


# --------------------------------------------------------------------------
# 5) backtest_horizon.py: kolumny baseline muszą istnieć i mieć sens.
# --------------------------------------------------------------------------
def test_backtest_horizon_baseline_columns_present(tmp_path):
    csv_path = tmp_path / "merged.csv"
    make_synthetic_hourly_csv(csv_path, n=250, target_col="PM10")

    model_out = tmp_path / "model.pkl"
    r = subprocess.run([
        sys.executable, str(SRC / "train_pm10_rf.py"),
        "--csv-path", str(csv_path), "--target", "PM10", "--time-col", "timestamp",
        "--lags", "1", "3", "--rolling", "3", "--n-estimators", "15",
        "--model-out", str(model_out), "--no-save-reports",
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    out_csv = tmp_path / "horizon_acc.csv"
    r = subprocess.run([
        sys.executable, str(SRC / "backtest_horizon.py"),
        "--csv-path", str(csv_path), "--model", str(model_out), "--target", "PM10",
        "--max-horizon", "6", "--step-hours", "12", "--out", str(out_csv),
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, f"backtest_horizon.py failed: {r.stderr}\n{r.stdout}"
    assert out_csv.exists()

    acc = pd.read_csv(out_csv)
    for col in ["mae", "baseline_mae", "baseline_rmse", "improvement_pct"]:
        assert col in acc.columns, f"Brak kolumny '{col}' w wynikach audytu"
    assert (acc["baseline_mae"] >= 0).all()


# --------------------------------------------------------------------------
# 6) merge_pm10_results.py --pollutant: właściwe nazwy kolumn dla PM10 i PM2.5.
# --------------------------------------------------------------------------
def test_merge_pm10_results_pollutant_pm25(tmp_path):
    back = tmp_path / "backtest.csv"
    pred = tmp_path / "pred.csv"
    weather = tmp_path / "weather.csv"
    out = tmp_path / "pm25_all_latest.csv"

    pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=5, freq="h"),
        "y_true": [1.0, 2.0, 3.0, 4.0, 5.0],
        "y_pred": [1.1, 2.1, 2.9, 4.2, 4.8],
    }).to_csv(back, index=False)

    pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01 05:00:00", periods=3, freq="h"),
        "pm25_pred": [5.5, 6.0, 6.5],
    }).to_csv(pred, index=False)

    pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=8, freq="h"),
        "temperatura": np.linspace(0, 7, 8),
    }).to_csv(weather, index=False)

    r = subprocess.run([
        sys.executable, str(SRC / "merge_pm10_results.py"),
        "--pollutant", "pm25",
        "--backtest", str(back), "--prediction", str(pred), "--weather", str(weather),
        "--time-col", "timestamp", "--coalesce-hist", "--out", str(out),
    ], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, f"merge_pm10_results.py --pollutant pm25 failed: {r.stderr}\n{r.stdout}"
    assert out.exists()

    df = pd.read_csv(out)
    assert {"pm25_true", "pm25_pred", "pm25_hist", "error"}.issubset(df.columns)
    assert "pm10_pred" not in df.columns
    assert df["pm25_pred"].notna().any()


# --------------------------------------------------------------------------
# 7) estimate_pm25_from_pm10.py: "awans" do realnych danych, gdy jest ich >=72.
# --------------------------------------------------------------------------
def test_estimate_pm25_graduates_to_real_data_when_enough(tmp_path, monkeypatch):
    mod = load_module_from_path("estimate_pm25_test", SRC / "estimate_pm25_from_pm10.py")

    merged_path = tmp_path / "merged_hourly.csv"
    n = 100
    ts = pd.date_range("2026-01-01", periods=n, freq="h")
    # >=72 realnych wartości PM2.5 (>= MIN_ROWS_TO_TRAIN)
    pm25 = np.linspace(1, 10, n)
    pm10 = np.linspace(5, 20, n)
    pd.DataFrame({"timestamp": ts, "PM2.5": pm25, "PM10": pm10}).to_csv(merged_path, index=False)

    out_csv = tmp_path / "merged_hourly_pm25_bootstrap.csv"
    out_meta = tmp_path / "pm25_bootstrap_meta.txt"

    monkeypatch.setattr(mod, "MERGED_PATH", merged_path)
    monkeypatch.setattr(mod, "OUT_CSV", out_csv)
    monkeypatch.setattr(mod, "OUT_META", out_meta)

    mod.main()

    assert out_csv.exists()
    result = pd.read_csv(out_csv)
    pd.testing.assert_series_equal(
        result["PM2.5"].reset_index(drop=True), pd.Series(pm25, name="PM2.5"), check_exact=False, atol=1e-9
    )
    assert not out_meta.exists(), "Meta bootstrap NIE powinno istnieć, gdy dane są już w pełni realne"


def test_estimate_pm25_falls_back_to_seasonal_ratio_when_scarce(tmp_path, monkeypatch):
    mod = load_module_from_path("estimate_pm25_test2", SRC / "estimate_pm25_from_pm10.py")

    merged_path = tmp_path / "merged_hourly.csv"
    syngeos_path = tmp_path / "syngeos_agg.csv"
    n = 100
    ts = pd.date_range("2026-01-15", periods=n, freq="h")  # styczeń = sezon grzewczy
    pm10 = np.full(n, 20.0)
    pd.DataFrame({"timestamp": ts, "PM10": pm10}).to_csv(merged_path, index=False)

    # 5 realnych par kalibracyjnych ze stałym stosunkiem PM2.5/PM10 = 0.5
    cal_ts = ts[:5]
    pd.DataFrame({
        "timestamp": cal_ts,
        "pm25_mean": [10.0] * 5,
        "pm25_count": [3] * 5,
    }).to_csv(syngeos_path, index=False)

    out_csv = tmp_path / "merged_hourly_pm25_bootstrap.csv"
    out_meta = tmp_path / "pm25_bootstrap_meta.txt"

    monkeypatch.setattr(mod, "MERGED_PATH", merged_path)
    monkeypatch.setattr(mod, "SYNGEOS_PATH", syngeos_path)
    monkeypatch.setattr(mod, "OUT_CSV", out_csv)
    monkeypatch.setattr(mod, "OUT_META", out_meta)

    mod.main()

    assert out_csv.exists()
    assert out_meta.exists(), "Meta bootstrap POWINNO istnieć, gdy danych jest za mało"
    result = pd.read_csv(out_csv)
    assert "PM2.5_is_estimated" in result.columns
    # z dala od punktów kalibracyjnych wartość musi być czystym szacunkiem: PM10 * ratio
    estimated_rows = result[result["PM2.5_is_estimated"] == True]  # noqa: E712
    assert not estimated_rows.empty
    assert (estimated_rows["PM2.5"] > 0).all()
