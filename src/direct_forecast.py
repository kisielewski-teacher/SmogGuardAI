# -*- coding: utf-8 -*-
"""
direct_forecast.py — prognoza PM10 "bezposrednia": osobny model na KAZDY horyzont 1..72 h.

Dlaczego? Poprzednia metoda (rekurencyjna) przewiduje tylko 1 godzine, a 72 h buduje
w petli, w ktorej wlasna prognoza wraca jako "wczorajsza wartosc" — bledy sie kumuluja.
Tutaj model h odpowiada od razu na pytanie "ile bedzie PM10 za h godzin?", wiec nie ma
petli. W uczciwym tescie na 2026 roku (dane niewidziane przy uczeniu, 477 punktow
startowych) blad na h+72 spadl z 7,0 do 6,1 ug/m3 (patrz outputs/experiment_*.csv).

Uzycie:
    py src/direct_forecast.py train   [--max-age-hours 24]   # uczy 72 modele -> models/pm10_direct.pkl
    py src/direct_forecast.py predict                         # dopisuje prognoze do outputs/pm10_pred_latest.csv

Funkcje load_grid / origin_features / target_time_features sa wspolne z eksperymentem
experiment_direct_horizon.py, wiec to, co testujemy, jest dokladnie tym, co dziala w produkcji.
"""
import argparse
import time
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
TARGET = "PM10"
WEATHER = ["temperatura", "predkosc_wiatru", "wilgotnosc_wzgledna", "cisnienie"]
WIND_DIR = "kierunek_wiatru"   # stopnie, skad wieje wiatr (0-360); 0 przy ciszy
LAGS = (0, 1, 2, 3, 6, 12, 24, 48)
ROLLS = (3, 6, 12, 24, 72)
PM10_MAX_PHYSICAL = 500.0
MODEL_PATH = BASE / "models" / "pm10_direct.pkl"
LGB_PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=40,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=42, verbose=-1)


def load_grid(csv_path: Path) -> pd.DataFrame:
    """Regularna siatka godzinowa (brakujace godziny = NaN), zeby shift() znaczylo dokladnie 'godzine wczesniej'."""
    df = pd.read_csv(csv_path, parse_dates=["timestamp"]).sort_values("timestamp")
    df = df.drop_duplicates("timestamp").set_index("timestamp")
    df = df[[TARGET] + [c for c in WEATHER + [WIND_DIR] if c in df.columns]].copy()
    df.loc[df[TARGET] > PM10_MAX_PHYSICAL, TARGET] = np.nan
    return df.asfreq("h")


def wind_features(df: pd.DataFrame) -> pd.DataFrame:
    """Kierunek wiatru jako liczby ciagle. Kat 359 i 1 stopien sa blisko siebie, a w stopniach wygladaja
    na odlegle, wiec uzywamy sinusa/cosinusa oraz skladowych wschod-zachod (u) i poludnie-polnoc (v):
    wiatr wieje SKAD kierunek, wiec np. wiatr z zachodu (270 st.) niesie powietrze na wschod (u > 0).
    Przy ciszy kierunek jest bez znaczenia (NaN)."""
    f = pd.DataFrame(index=df.index)
    if WIND_DIR not in df.columns or "predkosc_wiatru" not in df.columns:
        return f
    speed = df["predkosc_wiatru"]
    rad = np.deg2rad(df[WIND_DIR].where(speed > 0))
    f["wind_dir_sin"] = np.sin(rad)
    f["wind_dir_cos"] = np.cos(rad)
    f["wind_u"] = -speed * np.sin(rad)
    f["wind_v"] = -speed * np.cos(rad)
    # przeplyw usredniony z 12 h (stabilny kierunek napywu powietrza)
    f["wind_u_mean12"] = f["wind_u"].fillna(0).rolling(12, min_periods=6).mean()
    f["wind_v_mean12"] = f["wind_v"].fillna(0).rolling(12, min_periods=6).mean()
    return f


def origin_features(df: pd.DataFrame, use_wind: bool = True) -> pd.DataFrame:
    """Cechy znane w chwili t (teraz): przeszle PM10, pogoda, wiatr, pora roku/doby."""
    s = df[TARGET]
    f = pd.DataFrame(index=df.index)
    for L in LAGS:
        f[f"pm10_lag{L}"] = s.shift(L)
    for W in ROLLS:
        f[f"pm10_mean{W}"] = s.rolling(W, min_periods=max(1, W // 2)).mean()
        f[f"pm10_std{W}"] = s.rolling(W, min_periods=max(2, W // 2)).std()
    f["pm10_trend6"] = s - s.shift(6)
    for c in WEATHER:
        if c in df.columns:
            f[c] = df[c]
            f[f"{c}_d6"] = df[c] - df[c].shift(6)
    if use_wind:
        f = f.join(wind_features(df))
    h = df.index
    f["hour_sin"] = np.sin(2 * np.pi * h.hour / 24)
    f["hour_cos"] = np.cos(2 * np.pi * h.hour / 24)
    f["month_sin"] = np.sin(2 * np.pi * h.month / 12)
    f["month_cos"] = np.cos(2 * np.pi * h.month / 12)
    return f


NEIGHBORS_CSV = BASE / "data" / "neighbors_pm10.csv"
# stacje z pelna, ciagla historia PM10 od 2022 (pozostale mierza okresowo albo krocej)
NEIGHBOR_STATIONS = ["koszalin", "koscierzyna", "gdynia", "gdansk"]


def neighbor_features(index: pd.DatetimeIndex, path: Path = NEIGHBORS_CSV, stations=None) -> pd.DataFrame:
    """PM10 w sasiednich miastach (60-100 km): teraz, srednia 6 h i 24 h, zmiana w 6 h.

    Smog bywa niesiony wiatrem z innych miejsc, wiec stacja "w strone, skad wieje" moze zapowiadac to,
    co za kilka godzin dotrze do Slupska.
    """
    f = pd.DataFrame(index=index)
    if not Path(path).exists():
        return f
    nb = pd.read_csv(path, parse_dates=["timestamp"]).set_index("timestamp").reindex(index)
    for name in (stations or NEIGHBOR_STATIONS):
        if name not in nb.columns:
            continue
        s = pd.to_numeric(nb[name], errors="coerce")
        s = s.where(s.between(0, 500))
        f[f"nb_{name}"] = s
        f[f"nb_{name}_mean6"] = s.rolling(6, min_periods=3).mean()
        f[f"nb_{name}_mean24"] = s.rolling(24, min_periods=12).mean()
        f[f"nb_{name}_d6"] = s - s.shift(6)
    return f


# azymut (stopnie od polnocy, zgodnie z zegarem) od Slupska do stacji — do wyznaczenia stacji "pod wiatr"
NEIGHBOR_BEARING = {"koszalin": 242, "koscierzyna": 121, "gdynia": 83, "gdansk": 95}


def upwind_features(df: pd.DataFrame, path: Path = NEIGHBORS_CSV) -> pd.DataFrame:
    """PM10 w stacjach lezacych POD WIATR (tam, skad wieje) i jego nadwyzka nad Slupskiem.

    Stacja liczy sie tym mocniej, im blizej kierunku wiatru lezy (waga = cos^2 kata, 0 gdy kat > 90 st.).
    Gdy wiatr nie wieje z zadnej z tych stron albo jest cisza, cecha jest pusta (NaN).
    """
    f = pd.DataFrame(index=df.index)
    if not Path(path).exists() or WIND_DIR not in df.columns:
        return f
    nb = pd.read_csv(path, parse_dates=["timestamp"]).set_index("timestamp").reindex(df.index)
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    calm = ~(df["predkosc_wiatru"] > 0)
    for name, bearing in NEIGHBOR_BEARING.items():
        if name not in nb.columns:
            continue
        s = pd.to_numeric(nb[name], errors="coerce").where(lambda x: x.between(0, 500))
        s6 = s.rolling(6, min_periods=3).mean()
        diff = ((df[WIND_DIR] - bearing + 180) % 360) - 180
        w = (np.cos(np.deg2rad(diff)).clip(lower=0) ** 2).where(~calm & df[WIND_DIR].notna(), 0.0)
        ok = s6.notna()
        num = num + (w * s6).where(ok, 0.0)
        den = den + w.where(ok, 0.0)
    up = (num / den).where(den > 0.2)
    f["nb_upwind"] = up
    f["nb_upwind_w"] = den
    f["nb_upwind_excess"] = up - df[TARGET].rolling(6, min_periods=3).mean()
    return f


def future_weather_features(df: pd.DataFrame, h: int, noise: dict = None, seed: int = 0, smooth: int = 0) -> pd.DataFrame:
    """Pogoda na chwile t+h (dla modelu horyzontu h), w kolumnach f_*.

    W EKSPERYMENCIE bierzemy tu pogode ZMIERZONA w t+h, czyli udajemy idealna prognoze pogody. To GORNA
    GRANICA tego, co moze dac prognoza (prawdziwa prognoza ma bledy). `noise` (sd bledu na kolumne)
    pozwala dodac szum i zasymulowac nieidealna prognoze.
    """
    cols = {"temperatura": "f_temp", "cisnienie": "f_pres", "wilgotnosc_wzgledna": "f_rh", "predkosc_wiatru": "f_wspd"}
    f = pd.DataFrame(index=df.index)
    rng = np.random.default_rng(seed + h)
    # smooth > 0: srednia z ostatnich `smooth` godzin konczacych sie w t+h (spokojniejszy sygnal niz pojedyncza godzina)
    sm = (lambda s: s.rolling(smooth, min_periods=max(1, smooth // 2)).mean()) if smooth else (lambda s: s)
    for c, name in cols.items():
        if c in df.columns:
            v = sm(df[c]).shift(-h)
            if noise and c in noise:
                v = v + rng.normal(0, noise[c], len(v))
            f[name] = v
    if WIND_DIR in df.columns and "predkosc_wiatru" in df.columns:
        spd = df["predkosc_wiatru"].shift(-h)
        deg = df[WIND_DIR].shift(-h)
        rad0 = np.deg2rad(df[WIND_DIR].where(df["predkosc_wiatru"] > 0))
        u_all = -df["predkosc_wiatru"] * np.sin(rad0)
        v_all = -df["predkosc_wiatru"] * np.cos(rad0)
        if noise and WIND_DIR in noise:
            deg = deg + rng.normal(0, noise[WIND_DIR], len(deg))
        rad = np.deg2rad(deg.where(spd > 0))
        f["f_u"] = -spd * np.sin(rad)
        f["f_v"] = -spd * np.cos(rad)
        if smooth:
            f["f_u"] = sm(u_all.fillna(0)).shift(-h)
            f["f_v"] = sm(v_all.fillna(0)).shift(-h)
    if "cisnienie" in df.columns:
        f["f_dp"] = df["cisnienie"].shift(-h) - df["cisnienie"]   # tendencja cisnienia do t+h
    return f


def target_time_features(index: pd.DatetimeIndex, h: int) -> pd.DataFrame:
    """Pora doby/tygodnia/roku dla chwili, ktorej dotyczy prognoza (t+h) — znane z gory."""
    tt = index + pd.Timedelta(hours=h)
    return pd.DataFrame({
        "t_hour_sin": np.sin(2 * np.pi * tt.hour / 24),
        "t_hour_cos": np.cos(2 * np.pi * tt.hour / 24),
        "t_dow": tt.day_of_week,
        "t_weekend": (tt.day_of_week >= 5).astype(int),
        "t_month_sin": np.sin(2 * np.pi * tt.month / 12),
        "t_month_cos": np.cos(2 * np.pi * tt.month / 12),
    }, index=index)


def train_all(df: pd.DataFrame, max_h: int = 72, train_start=None, train_end=None, use_wind: bool = True,
              **lgb_overrides) -> dict:
    """Uczy modele h=1..max_h na danych [train_start, train_end). Zwraca {h: model}."""
    feats = origin_features(df, use_wind)
    y = df[TARGET]
    models = {}
    for h in range(1, max_h + 1):
        X = pd.concat([feats, target_time_features(df.index, h)], axis=1)
        y_h = y.shift(-h)
        mask = y_h.notna().to_numpy().copy()
        if train_start is not None:
            mask &= np.asarray(df.index >= train_start)
        if train_end is not None:
            mask &= np.asarray(df.index + pd.Timedelta(hours=h) < train_end)
        if mask.sum() < 200:
            raise RuntimeError(f"Za malo danych do uczenia horyzontu h={h} ({int(mask.sum())} wierszy).")
        m = lgb.LGBMRegressor(n_jobs=-1, **{**LGB_PARAMS, **lgb_overrides})
        m.fit(X[mask], y_h[mask])
        models[h] = m
    return models


def fit_interval_h(index, X, y_h, h: int, train_start, train_end, calib_days: int = 365,
                   n_estimators: int = 200, coverage: float = 0.8):
    """Przedzial niepewnosci dla jednego horyzontu: modele kwantylowe 10% i 90% + kalibracja.

    Surowe modele kwantylowe bywaja zbyt waskie poza probą (zamiast 80% pokrywaja ok. 73%).
    Dlatego ostatnie `calib_days` dni danych uczacych zostawiamy do KALIBRACJI (metoda conformal,
    CQR): modele uczymy na starszych danych, mierzymy na kalibracyjnych, o ile przedzial sie myli
    i o tyle go poszerzamy (poprawka Q). Zwraca (model_dolny, model_gorny, Q).
    """
    valid = y_h.notna().to_numpy()
    idx = np.asarray(index)
    start = np.datetime64(train_start) if train_start is not None else idx.min()
    end = np.datetime64(train_end)
    calib_start = end - np.timedelta64(int(calib_days), "D")
    hh = np.timedelta64(int(h), "h")
    fit_mask = valid & (idx >= start) & (idx + hh < calib_start)
    cal_mask = valid & (idx >= calib_start) & (idx + hh < end)
    if fit_mask.sum() < 200 or cal_mask.sum() < 50:
        raise RuntimeError(f"Za malo danych do przedzialu dla h={h} (uczenie {int(fit_mask.sum())}, kalibracja {int(cal_mask.sum())}).")
    params = {**LGB_PARAMS, "n_estimators": n_estimators}
    lo = lgb.LGBMRegressor(n_jobs=-1, objective="quantile", alpha=0.1, **params).fit(X[fit_mask], y_h[fit_mask])
    hi = lgb.LGBMRegressor(n_jobs=-1, objective="quantile", alpha=0.9, **params).fit(X[fit_mask], y_h[fit_mask])
    p_lo, p_hi = lo.predict(X[cal_mask]), hi.predict(X[cal_mask])
    lower, upper = np.minimum(p_lo, p_hi), np.maximum(p_lo, p_hi)
    y = y_h[cal_mask].to_numpy()
    scores = np.maximum(lower - y, y - upper)          # >0: wartosc wypadla poza przedzialem
    n = len(scores)
    level = min(1.0, np.ceil((n + 1) * coverage) / n)
    return lo, hi, float(np.quantile(scores, level))


def apply_interval(models_h, X, point: np.ndarray):
    """Zastosuj przedzial (model_dolny, model_gorny, Q) do cech X; punkt prognozy zawsze w srodku."""
    lo_m, hi_m, q = models_h
    a, b = lo_m.predict(X), hi_m.predict(X)
    lower = np.minimum(a, b) - q
    upper = np.maximum(a, b) + q
    lower = np.maximum(np.minimum(lower, point), 0.0)
    upper = np.maximum(upper, point)
    return lower, upper


def train_intervals(df: pd.DataFrame, max_h: int = 72, train_start=None, train_end=None, use_wind: bool = True,
                    **kw) -> dict:
    feats = origin_features(df, use_wind)
    y = df[TARGET]
    end = train_end if train_end is not None else df.index.max()
    out = {}
    for h in range(1, max_h + 1):
        X = pd.concat([feats, target_time_features(df.index, h)], axis=1)
        out[h] = fit_interval_h(df.index.values, X, y.shift(-h), h, train_start, end, **kw)
    return out


def predict_future(models: dict, df: pd.DataFrame, use_wind: bool = True, intervals: dict = None) -> pd.DataFrame:
    """Prognoza od ostatniej godziny z pomiarem PM10 (t0) na h=1..max_h godzin do przodu."""
    last_valid = df[TARGET].last_valid_index()
    if last_valid is None:
        raise RuntimeError("Brak jakiegokolwiek pomiaru PM10.")
    feats = origin_features(df, use_wind).loc[[last_valid]]
    rows = []
    for h, m in sorted(models.items()):
        X = pd.concat([feats, target_time_features(feats.index, h)], axis=1)
        point = float(max(0.0, m.predict(X)[0]))
        row = {"timestamp": last_valid + pd.Timedelta(hours=h), "pm10_pred": point}
        if intervals and h in intervals:
            lo, hi = apply_interval(intervals[h], X, np.array([point]))
            row["pm10_pred_low"], row["pm10_pred_high"] = float(lo[0]), float(hi[0])
        rows.append(row)
    return pd.DataFrame(rows)


def cmd_train(args):
    if MODEL_PATH.exists() and args.max_age_hours > 0:
        age_h = (time.time() - MODEL_PATH.stat().st_mtime) / 3600
        if age_h < args.max_age_hours:
            print(f"[INFO] Model bezposredni ma {age_h:.1f} h (< {args.max_age_hours} h) - pomijam uczenie.")
            return
    df = load_grid(Path(args.csv_path))
    start = df.index.max() - pd.Timedelta(days=int(round(365.25 * args.train_years)))
    models = train_all(df, args.max_horizon, train_start=start, use_wind=not args.no_wind)
    intervals = train_intervals(df, args.max_horizon, train_start=start, use_wind=not args.no_wind)
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump({"models": models, "intervals": intervals, "trained_at": pd.Timestamp.now().isoformat(),
                 "train_start": str(start), "train_end": str(df.index.max()), "use_wind": not args.no_wind}, MODEL_PATH, compress=3)
    print(f"[OK] Nauczono {len(models)} modeli (h=1..{args.max_horizon}) na danych od {start.date()} -> {MODEL_PATH}")


def cmd_predict(args):
    if not MODEL_PATH.exists():
        print("[WARN] Brak modelu bezposredniego - uruchom: py src/direct_forecast.py train. Zostaje prognoza rekurencyjna.")
        return
    bundle = joblib.load(MODEL_PATH)
    df = load_grid(Path(args.csv_path))
    fc = predict_future(bundle["models"], df, use_wind=bundle.get("use_wind", False),
                        intervals=bundle.get("intervals"))
    out_path = Path(args.out)
    if out_path.exists():
        old = pd.read_csv(out_path, parse_dates=["timestamp"])
        # historia (dopasowanie modelu do przeszlosci) zostaje, przyszlosc = nowa prognoza bezposrednia
        old = old[old["timestamp"] < fc["timestamp"].min()]
        # historia nie ma przedzialu (kolumny low/high puste), przyszlosc ma
        fc = pd.concat([old[["timestamp", "pm10_pred"]], fc], ignore_index=True)
    fc = fc.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
    fc.to_csv(out_path, index=False, date_format="%Y-%m-%d %H:%M:%S")
    print(f"[OK] Zapisano prognoze bezposrednia ({len(bundle['models'])} godzin) do {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Prognoza PM10 bezposrednia (osobny model na kazdy horyzont)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--csv-path", default=str(BASE / "data" / "merged_hourly.csv"))
    t.add_argument("--train-years", type=float, default=4.0)
    t.add_argument("--max-horizon", type=int, default=72)
    t.add_argument("--no-wind", action="store_true", help="Bez cech kierunku wiatru (do porownan).")
    t.add_argument("--max-age-hours", type=float, default=24.0,
                   help="Pomin uczenie, jesli model jest mlodszy niz tyle godzin (0 = zawsze ucz).")
    t.set_defaults(fn=cmd_train)
    p = sub.add_parser("predict")
    p.add_argument("--csv-path", default=str(BASE / "data" / "merged_hourly.csv"))
    p.add_argument("--out", default=str(BASE / "outputs" / "pm10_pred_latest.csv"))
    p.set_defaults(fn=cmd_predict)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
