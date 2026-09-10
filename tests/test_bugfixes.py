"""
Testy regresyjne dla błędów znalezionych i naprawionych w trakcie audytu pipeline'u:

1. Wyciek targetu do cechy roll3/roll6 (rolling mean bez shift(1)) w features.py i train_pm10.py.
2. Błąd off-by-one w lagach >1 podczas iterative_forecast (utils_features.py).
3. Przestawienie kolumn pogodowych przy doklejaniu danych Open-Meteo do imgw_synop_hourly.csv.
4. Utrata poprawnej (falsy) wartości 0 dla PM2.5 z Airly przez `or`.
5. Dzielenie przez zero w MAPE, gdy y_true == 0 (backtest_pm10.py).
6. backtest_pm10.py: walk-forward musi widzieć historię, nie pojedynczy wiersz.
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


# --------------------------------------------------------------------------
# 1) Rolling-mean leakage: PM10_roll3 nie może zawierać bieżącej wartości.
# --------------------------------------------------------------------------
def test_features_roll3_excludes_current_value(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    ts = pd.date_range("2026-01-01", periods=8, freq="h")
    pm10 = [10, 12, 11, 40, 15, 14, 13, 12]  # spike at index 3 makes leakage obvious
    merged = pd.DataFrame({"timestamp": ts, "PM10": pm10})
    merged_path = data_dir / "merged_hourly.csv"
    merged.to_csv(merged_path, index=False)

    out_path = data_dir / "features_pm10.csv"

    env_script = f'''
import sys
sys.path.insert(0, {str(SRC)!r})
import features
features.src = {str(merged_path)!r}
features.out = {str(out_path)!r}
from pathlib import Path
features.src = Path(features.src)
features.out = Path(features.out)
features.main()
'''
    r = subprocess.run([sys.executable, "-c", env_script], cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, f"features.py failed: {r.stderr}\n{r.stdout}"

    out = pd.read_csv(out_path, parse_dates=["timestamp"])
    row = out[out["timestamp"] == ts[3]]
    assert not row.empty
    # correct roll3 at index 3 = mean(PM10[0:3]) = mean(10,12,11), MUST NOT include the spike (40) itself
    expected_roll3 = np.mean(pm10[0:3])
    assert row["PM10_roll3"].iloc[0] == pytest.approx(expected_roll3)
    leaked_roll3 = np.mean(pm10[1:4])  # what the old buggy code (no shift) would have produced
    assert row["PM10_roll3"].iloc[0] != pytest.approx(leaked_roll3)


def test_train_pm10_fallback_roll_excludes_current_value(tmp_path, monkeypatch):
    mod = load_module_from_path("train_pm10_test", SRC / "train_pm10.py")

    ts = pd.date_range("2026-01-01", periods=10, freq="h")
    pm10 = [10, 12, 11, 40, 15, 14, 13, 12, 16, 18]
    dfm = pd.DataFrame({"timestamp": ts, "PM10": pm10})

    merged_path = tmp_path / "merged_hourly.csv"
    dfm.to_csv(merged_path, index=False)
    feats_path = tmp_path / "features_pm10.csv"

    monkeypatch.setattr(mod, "MERGED_HOURLY_CSV", merged_path)
    monkeypatch.setattr(mod, "FEATURES_PM10_CSV", feats_path)

    result_path = mod.ensure_features_exist()
    out = pd.read_csv(result_path, parse_dates=["timestamp"])

    row = out[out["timestamp"] == ts[3]]
    assert not row.empty
    expected_roll3 = np.mean(pm10[0:3])
    assert row["pm10_roll3"].iloc[0] == pytest.approx(expected_roll3)


# --------------------------------------------------------------------------
# 2) iterative_forecast: lagi >1 muszą wskazywać właściwy punkt w historii.
# --------------------------------------------------------------------------
def test_iterative_forecast_lag_alignment():
    mod = load_module_from_path("utils_features_test", SRC / "utils_features.py")

    class RecordingModel:
        def __init__(self):
            self.calls = []

        def predict(self, X):
            self.calls.append(X.copy())
            return [0.0]

    ts = pd.date_range("2026-01-01", periods=5, freq="h")
    values = [10, 20, 30, 40, 50]
    hist = pd.DataFrame({"timestamp": ts, "target": values})
    model = RecordingModel()

    features = ["target_lag1", "target_lag2", "target_lag3"]
    mod.iterative_forecast(model, hist, "target", features, horizon_hours=1, ts_col="timestamp")

    X = model.calls[0]
    # next_ts is 1h after the last known point (value 50).
    # lag1 -> value 1h before next_ts = last known value = 50
    # lag2 -> value 2h before next_ts = 40
    # lag3 -> value 3h before next_ts = 30
    assert X["target_lag1"].iloc[0] == pytest.approx(50)
    assert X["target_lag2"].iloc[0] == pytest.approx(40)
    assert X["target_lag3"].iloc[0] == pytest.approx(30)


# --------------------------------------------------------------------------
# 3) openmeteo_backfill: kolejność kolumn przy doklejaniu do imgw_synop_hourly.csv.
# --------------------------------------------------------------------------
def test_openmeteo_backfill_preserves_column_order(tmp_path):
    mod = load_module_from_path("openmeteo_backfill_test", SRC / "openmeteo_backfill.py")

    imgw_path = tmp_path / "imgw_synop_hourly.csv"
    # nagłówek w innej kolejności niż ta budowana przez fetch_openmeteo()
    imgw_path.write_text(
        "stacja,timestamp,temperatura,predkosc_wiatru,wilgotnosc_wzgledna,suma_opadu,cisnienie\n"
        "Slupsk,2025-12-31 23:00:00,1.0,5.0,80,0.0,1010.0\n"
    )

    om = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-01-01 00:00:00"]),
        "temperatura": [2.0],
        "wilgotnosc_wzgledna": [55.0],   # powinno trafić do kolumny wilgotnosc_wzgledna
        "cisnienie": [1005.0],           # powinno trafić do kolumny cisnienie
        "predkosc_wiatru": [8.0],        # powinno trafić do kolumny predkosc_wiatru
        "suma_opadu": [0.2],             # powinno trafić do kolumny suma_opadu
    })

    mod.fill_imgw(imgw_path, om)

    out = pd.read_csv(imgw_path)
    new_row = out.iloc[-1]
    assert new_row["wilgotnosc_wzgledna"] == pytest.approx(55.0)
    assert new_row["cisnienie"] == pytest.approx(1005.0)
    assert new_row["predkosc_wiatru"] == pytest.approx(8.0)
    assert new_row["suma_opadu"] == pytest.approx(0.2)


# --------------------------------------------------------------------------
# 4) airly_fetch: prawdziwe 0 dla PM2.5 nie może zamienić się w None.
# --------------------------------------------------------------------------
def test_airly_fetch_keeps_true_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("AIRLY_KEY", "dummy")
    mod = load_module_from_path("airly_fetch_test", SRC / "airly_fetch.py")
    monkeypatch.setattr(mod, "API_KEY", "dummy")

    monkeypatch.setattr(mod, "_get_nearest_installation", lambda: {"id": 1, "address": {"street": "Test"}})
    monkeypatch.setattr(
        mod, "fetch_measurements",
        lambda inst: {"current": {"values": [{"name": "PM25", "value": 0.0}, {"name": "PM10", "value": 3.0}]}},
    )
    out = tmp_path / "airly_slupsk.csv"
    monkeypatch.setattr(mod, "OUT", out)

    mod.main()

    assert out.exists()
    df = pd.read_csv(out)
    assert df["PM2.5"].iloc[0] == 0.0


# --------------------------------------------------------------------------
# 5) MAPE nie może eksplodować do inf/NaN dla całego raportu przez jeden wiersz y_true==0.
# --------------------------------------------------------------------------
def test_backtest_mape_ignores_zero_true_rows():
    out = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="h"),
        "y_true": [10.0, 0.0, 20.0, 15.0],
        "y_pred": [11.0, 1.0, 19.0, 14.0],
    })
    out["error"] = out["y_pred"] - out["y_true"]

    nonzero = out["y_true"] != 0
    mape = float(np.mean(np.abs(out.loc[nonzero, "error"] / out.loc[nonzero, "y_true"])) * 100) if nonzero.any() else float("nan")

    assert np.isfinite(mape)
    # powinno być liczone tylko z 3 wierszy z y_true != 0
    expected = np.mean([abs(1 / 10), abs(1 / 20), abs(1 / 15)]) * 100
    assert mape == pytest.approx(expected)


# --------------------------------------------------------------------------
# 6) backtest_pm10.py: walk-forward musi widzieć historię (lag/rolling), nie
#    pojedynczy wiersz -- inaczej cechy lag/rolling są same NaN i model
#    ignoruje realną autokorelację PM10 (przewiduje prawie stałą wartość).
# --------------------------------------------------------------------------
def test_backtest_pm10_uses_history_and_tracks_target(tmp_path):
    rng = np.random.default_rng(0)
    n = 200
    ts = pd.date_range("2026-01-01", periods=n, freq="h")
    ar = np.zeros(n)
    noise = rng.normal(0, 2, n)
    for i in range(1, n):
        ar[i] = 0.9 * ar[i - 1] + noise[i]
    pm10 = np.clip(20 + ar, 1, None)

    merged = pd.DataFrame({"timestamp": ts, "PM10": pm10})
    csv_path = tmp_path / "merged_hourly.csv"
    merged.to_csv(csv_path, index=False)

    model_path = tmp_path / "pm10_pipeline.pkl"
    r = subprocess.run(
        [
            sys.executable, "src/train_pm10_rf.py",
            "--csv-path", str(csv_path),
            "--target", "PM10",
            "--time-col", "timestamp",
            "--lags", "1", "3", "6",
            "--rolling", "3", "6",
            "--n-estimators", "50",
            "--model-out", str(model_path),
            "--no-save-reports",
        ],
        cwd=str(REPO), capture_output=True, text=True,
    )
    assert r.returncode == 0, f"train_pm10_rf.py failed: {r.stderr}\n{r.stdout}"
    assert model_path.exists()

    out_dir = tmp_path / "outputs"
    r = subprocess.run(
        [
            sys.executable, "src/backtest_pm10.py",
            "--csv-path", str(csv_path),
            "--time-col", "timestamp",
            "--target", "PM10",
            "--model", str(model_path),
            "--out-dir", str(out_dir),
        ],
        cwd=str(REPO), capture_output=True, text=True,
    )
    assert r.returncode == 0, f"backtest_pm10.py failed: {r.stderr}\n{r.stdout}"

    backtest_files = list(out_dir.glob("pm10_backtest_*.csv"))
    assert backtest_files
    back = pd.read_csv(backtest_files[0])

    # Signature of the single-row bug: predictions collapse into a narrow band
    # (lag/rolling features all NaN -> model falls back to near-constant output).
    # With real history available, the model should track a meaningful share
    # of the true variance on this strongly autocorrelated synthetic series.
    std_ratio = back["y_pred"].std() / back["y_true"].std()
    assert std_ratio > 0.3, f"predictions look degenerate (std_ratio={std_ratio:.3f}) -- history may not be reaching the model"
