import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import direct_forecast as df_  # noqa: E402


def _synthetic_csv(tmp_path, n=1500, gap=None):
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    rng = np.random.default_rng(0)
    pm = 20 + 10 * np.sin(np.arange(n) / 24 * 2 * np.pi) + rng.normal(0, 2, n)
    d = pd.DataFrame({"timestamp": idx, "PM10": pm,
                      "temperatura": 5 + rng.normal(0, 1, n), "predkosc_wiatru": 3 + rng.normal(0, 1, n),
                      "wilgotnosc_wzgledna": 80.0, "cisnienie": 1010.0})
    if gap:
        d.loc[gap[0]:gap[1], "PM10"] = np.nan
    p = tmp_path / "merged.csv"
    d.to_csv(p, index=False)
    return p


def test_train_and_predict_72h_shape_and_values(tmp_path):
    grid = df_.load_grid(_synthetic_csv(tmp_path))
    models = df_.train_all(grid, max_h=6, n_estimators=20)
    fc = df_.predict_future(models, grid)
    assert list(fc["timestamp"]) == [grid.index[-1] + pd.Timedelta(hours=h) for h in range(1, 7)]
    assert (fc["pm10_pred"] >= 0).all() and np.isfinite(fc["pm10_pred"]).all()


def test_predict_starts_after_last_valid_measurement_and_survives_gaps(tmp_path):
    # ostatnie 5 godzin bez pomiaru + dziura w srodku: lagi nie moga sie "przesunac"
    n = 1500
    grid = df_.load_grid(_synthetic_csv(tmp_path, n=n, gap=(700, 760)))
    grid.iloc[-5:, grid.columns.get_loc("PM10")] = np.nan
    models = df_.train_all(grid, max_h=3, n_estimators=20)
    fc = df_.predict_future(models, grid)
    t0 = grid.index[-6]
    assert fc["timestamp"].iloc[0] == t0 + pd.Timedelta(hours=1)
    feats = df_.origin_features(grid)
    assert np.isnan(feats["pm10_lag0"].iloc[705])      # w dziurze lag jest pusty, a nie z innej godziny


def test_predict_keeps_history_and_replaces_future(tmp_path, monkeypatch):
    csv = _synthetic_csv(tmp_path)
    grid = df_.load_grid(csv)
    models = df_.train_all(grid, max_h=4, n_estimators=10)
    model_path = tmp_path / "m.pkl"
    import joblib
    joblib.dump({"models": models}, model_path)
    monkeypatch.setattr(df_, "MODEL_PATH", model_path)
    out = tmp_path / "pred.csv"
    last = grid.index[-1]
    old = pd.DataFrame({"timestamp": pd.date_range(last - pd.Timedelta(hours=9), periods=14, freq="h"),
                        "pm10_pred": 999.0})
    old.to_csv(out, index=False)
    monkeypatch.setattr(sys, "argv", ["direct_forecast.py", "predict", "--csv-path", str(csv), "--out", str(out)])
    df_.main()
    res = pd.read_csv(out, parse_dates=["timestamp"])
    assert res["timestamp"].is_unique and res["timestamp"].is_monotonic_increasing
    hist = res[res["timestamp"] <= last]
    assert (hist["pm10_pred"] == 999.0).all() and len(hist) == 10       # historia nietknieta
    fut = res[res["timestamp"] > last]
    assert len(fut) == 4 and (fut["pm10_pred"] != 999.0).all()          # przyszlosc = nowa prognoza


def test_wind_features_direction_components_and_calm():
    idx = pd.date_range("2026-01-01", periods=4, freq="h")
    g = pd.DataFrame({"PM10": 10.0, "predkosc_wiatru": [4.0, 4.0, 4.0, 0.0],
                      "kierunek_wiatru": [270.0, 90.0, 360.0, 0.0]}, index=idx)
    w = df_.wind_features(g)
    assert w["wind_u"].iloc[0] > 3.9 and abs(w["wind_v"].iloc[0]) < 1e-9     # z zachodu niesie na wschod
    assert w["wind_u"].iloc[1] < -3.9                                         # ze wschodu na zachod
    assert w["wind_v"].iloc[2] < -3.9                                         # z polnocy na poludnie
    assert np.isnan(w["wind_dir_sin"].iloc[3])                                # cisza: kierunek bez znaczenia
    assert np.isclose(np.sin(np.deg2rad(359)), -np.sin(np.deg2rad(1)))       # 359 i 1 st. sa blisko siebie


def test_origin_features_without_wind_column_still_works():
    idx = pd.date_range("2026-01-01", periods=100, freq="h")
    g = pd.DataFrame({"PM10": np.arange(100.0), "temperatura": 5.0}, index=idx)
    f = df_.origin_features(g, use_wind=True)
    assert not any(c.startswith("wind_") for c in f.columns)


def test_interval_contains_point_is_nonnegative_and_calibration_widens(tmp_path):
    grid = df_.load_grid(_synthetic_csv(tmp_path, n=2000))
    feats = df_.origin_features(grid)
    h = 3
    X = pd.concat([feats, df_.target_time_features(grid.index, h)], axis=1)
    y_h = grid["PM10"].shift(-h)
    iv = df_.fit_interval_h(grid.index.values, X, y_h, h, None, grid.index.max(), calib_days=25, n_estimators=30)
    assert np.isfinite(iv[2])
    point = np.full(len(X.iloc[-50:]), 20.0)
    lo, hi = df_.apply_interval(iv, X.iloc[-50:], point)
    assert (lo >= 0).all() and (lo <= point).all() and (hi >= point).all()
    lo0, hi0 = df_.apply_interval((iv[0], iv[1], 0.0), X.iloc[-50:], point)
    assert np.allclose((hi - lo) - (hi0 - lo0), 0, atol=2 * abs(iv[2]) + 1e-9)


def test_predict_future_returns_interval_columns(tmp_path):
    grid = df_.load_grid(_synthetic_csv(tmp_path, n=2000))
    models = df_.train_all(grid, max_h=3, n_estimators=20)
    ints = df_.train_intervals(grid, max_h=3, calib_days=25, n_estimators=30)
    fc = df_.predict_future(models, grid, intervals=ints)
    assert {"pm10_pred_low", "pm10_pred_high"} <= set(fc.columns)
    assert (fc["pm10_pred_low"] <= fc["pm10_pred"]).all() and (fc["pm10_pred"] <= fc["pm10_pred_high"]).all()


def test_future_weather_features_are_shifted_by_h_and_noise_is_reproducible():
    idx = pd.date_range("2026-01-01", periods=30, freq="h")
    g = pd.DataFrame({"PM10": 10.0, "temperatura": np.arange(30.0), "predkosc_wiatru": 4.0,
                      "kierunek_wiatru": 270.0, "cisnienie": 1000.0 + np.arange(30.0)}, index=idx)
    f = df_.future_weather_features(g, 5)
    assert f["f_temp"].iloc[0] == 5.0                 # pogoda z chwili t+5
    assert f["f_temp"].iloc[-5:].isna().all()         # w ostatnich godzinach przyszlosci jeszcze nie ma
    assert f["f_dp"].iloc[0] == 5.0                   # tendencja cisnienia t -> t+5
    assert f["f_u"].iloc[0] > 3.9                     # wiatr z zachodu -> skladowa u > 0
    n1 = df_.future_weather_features(g, 5, noise={"temperatura": 1.5})
    n2 = df_.future_weather_features(g, 5, noise={"temperatura": 1.5})
    assert np.allclose(n1["f_temp"].dropna(), n2["f_temp"].dropna()) and not np.allclose(n1["f_temp"].dropna(), f["f_temp"].dropna())


def _neighbors_csv(tmp_path, n=100):
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    d = pd.DataFrame({"timestamp": idx, "koszalin": 10.0, "koscierzyna": 20.0, "gdynia": 30.0, "gdansk": 40.0})
    p = tmp_path / "neighbors.csv"
    d.to_csv(p, index=False)
    return p


def test_neighbor_features_columns_and_alignment(tmp_path):
    idx = pd.date_range("2026-01-01", periods=100, freq="h")
    nb = df_.neighbor_features(idx, path=_neighbors_csv(tmp_path))
    assert {"nb_koszalin", "nb_koszalin_mean6", "nb_gdansk_d6"} <= set(nb.columns)
    assert (nb["nb_gdynia"] == 30.0).all() and np.isclose(nb["nb_gdynia_d6"].dropna(), 0).all()
    assert df_.neighbor_features(idx, path=tmp_path / "brak.csv").shape[1] == 0     # brak pliku = brak cech, bez bledu


def test_upwind_feature_picks_station_the_wind_comes_from(tmp_path):
    p = _neighbors_csv(tmp_path)
    idx = pd.date_range("2026-01-01", periods=100, freq="h")
    base = {"PM10": 15.0, "predkosc_wiatru": 4.0}
    west = pd.DataFrame({**base, "kierunek_wiatru": 242.0}, index=idx)          # wiatr dokladnie od Koszalina
    assert np.allclose(df_.upwind_features(west, path=p)["nb_upwind"].dropna(), 10.0)
    east = pd.DataFrame({**base, "kierunek_wiatru": 89.0}, index=idx)           # od wschodu: Gdynia/Gdansk/Koscierzyna
    up = df_.upwind_features(east, path=p)["nb_upwind"].dropna()
    assert (up > 20).all() and (up < 40).all()
    calm = pd.DataFrame({"PM10": 15.0, "predkosc_wiatru": 0.0, "kierunek_wiatru": 90.0}, index=idx)
    assert df_.upwind_features(calm, path=p)["nb_upwind"].isna().all()           # cisza: brak kierunku napywu
