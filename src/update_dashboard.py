
# -*- coding: utf-8 -*-
"""
update_dashboard.py – pełny przebieg:
1) Future template (X godzin),
2) Predict przyszłość,
3) Backtest historii,
4) Merge w pm10_all_latest.csv.
Uruchomienie:
python src/update_dashboard.py --hours 24 --copy-last
"""

import os
import subprocess
import sys
from datetime import datetime
import glob
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def run(cmd):
    print(">>>", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)

def newest(pattern):
    files = glob.glob(os.path.join(ROOT, pattern))
    if not files:
        return None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]

def main(hours=24, copy_last=False, sep=",", encoding="utf-8"):
    # 0) (opcjonalnie) Pobierz dane z Syngeos — widget publiczny (deviceId=623)
    try:
        # pobierz kilka urządzeń Syngeos i zapisz agregat godzinowy (pm2.5/pm10)
        run([
            sys.executable, "src\\syngeos_fetch.py",
            "--devices", "411,189,623",
            "--out", "data\\syngeos_all.csv",
            "--aggregate", "data\\syngeos_agg.csv",
            "--resample", "H",
            "--verbose",
        ])
    except Exception as e:
        print("[WARN] syngeos_fetch nie powiódł się — kontynuuję pipeline:", e)

    # 1) Future template
    cmd_template = [
        sys.executable, "src\\make_future_template.py",
        "--history-csv", "data\\merged_hourly.csv",
        "--time-col", "timestamp",
        "--target", "PM10",
        "--hours", str(hours),
        "--sep", sep, "--encoding", encoding,
        "--out", "data\\future_hours.csv",
    ]
    if copy_last:
        cmd_template.append("--copy-last")
    run(cmd_template)

    # 2) Predict (wywołanie zgodne z aktualnym `predict_pm10.py`)
    run([
        sys.executable, "src\\predict_pm10.py",
        "--features", "data\\features_pm10.csv",
        "--model", "models\\pm10_pipeline.pkl",
        "--out", "outputs\\pm10_pred_latest.csv",
        "--time-col", "timestamp",
        "--horizon", str(hours),
        "--align-to", "data\\aqicn_slupsk_data.csv",
        "--verbose",
    ])

    # 3) Backtest
    run([
        sys.executable, "src\\backtest_pm10.py",
        "--csv-path", "data\\merged_hourly.csv",
        "--time-col", "timestamp",
        "--target", "PM10",
        "--model", "models\\pm10_pipeline.pkl",
        "--sep", sep, "--encoding", encoding,
        "--out-dir", "outputs",
    ])

    # 3b) PM2.5: jeśli model istnieje — uruchom predict_pm25.py; jeśli nie — spróbuj wytrenować,
    # a gdy to się nie uda — wygeneruj prostą prognozę zastępczą (persistence / średnia ostatnich N)
    pm25_model = os.path.join(ROOT, "models", "pm25_rf.pkl")
    forecast_pm25_path = os.path.join(ROOT, "data", "forecast_pm25.csv")

    trained = False
    if os.path.exists(pm25_model):
        trained = True
    else:
        print("[INFO] Brak modelu PM2.5 — spróbuję uruchomić trening (train_pm25.py)")
        try:
            run([sys.executable, "src\\train_pm25.py"])
        except Exception as e:
            print("[WARN] Training PM2.5 nie powiódł się:", e)
            trained = os.path.exists(pm25_model)

    if trained:
        try:
            run([sys.executable, "src\\predict_pm25.py"])
        except Exception as e:
            print("[WARN] predict_pm25.py nie powiódł się:", e)

    # Jeżeli nadal brak pliku prognozy PM2.5 — stwórz fallback (persistence z merged_hourly lub syngeos_agg)
    if not os.path.exists(forecast_pm25_path):
        print("[WARN] Brak forecast_pm25.csv — tworzenie prostego fallback'u (persistence/średnia)")
        try:
            import pandas as _pd
            merged = _pd.read_csv(os.path.join(ROOT, "data", "merged_hourly.csv"), parse_dates=["timestamp"]) if os.path.exists(os.path.join(ROOT, "data", "merged_hourly.csv")) else _pd.DataFrame()
            last_val = None
            last_ts = None
            # szukaj kolumny pm25 / PM2.5
            if not merged.empty:
                for col in ["pm25", "PM2.5", "PM2_5", "pm_25"]:
                    if col in merged.columns and merged[col].notna().any():
                        s = merged[merged[col].notna()].sort_values("timestamp")
                        last_ts = s["timestamp"].iloc[-1]
                        last_val = float(s[col].iloc[-1])
                        break
            # fallback: użyj syngeos_agg.csv (pm25_mean)
            if last_val is None and os.path.exists(os.path.join(ROOT, "data", "syngeos_agg.csv")):
                sa = _pd.read_csv(os.path.join(ROOT, "data", "syngeos_agg.csv"), parse_dates=["timestamp"]) if os.path.exists(os.path.join(ROOT, "data", "syngeos_agg.csv")) else _pd.DataFrame()
                if not sa.empty and "pm25_mean" in sa.columns and sa["pm25_mean"].notna().any():
                    s2 = sa[sa["pm25_mean"].notna()].sort_values("timestamp")
                    last_ts = s2["timestamp"].iloc[-1]
                    last_val = float(s2["pm25_mean"].iloc[-1])
            # jeśli mamy wartość — stwórz prognozę naive
            if last_val is None:
                print("[WARN] Brak danych historycznych PM2.5 do wygenerowania fallback'u. Pomijam.")
            else:
                rows = []
                import datetime as _dt
                base = _pd.to_datetime(last_ts)
                for h in range(1, int(hours) + 1):
                    rows.append({"timestamp": (base + _pd.Timedelta(hours=h)).strftime("%Y-%m-%d %H:%M:%S"), "pm25_pred": last_val})
                _pd.DataFrame(rows).to_csv(forecast_pm25_path, index=False)
                print(f"[OK] Zapisano fallback prognozy PM2.5 do: {forecast_pm25_path}")
        except Exception as e:
            print("[WARN] Nie udało się stworzyć fallback prognozy PM2.5:", e)

    # 4) Merge – wybierz najnowszy predykcyjny plik (timestamped) lub fallback na pm10_pred_latest.csv
    pred_path = newest("outputs\\pm10_pred_*.csv")
    if not pred_path:
        # fallback: najnowszy stały plik `pm10_pred_latest.csv`
        latest_candidate = os.path.join(ROOT, "outputs", "pm10_pred_latest.csv")
        pred_path = latest_candidate if os.path.exists(latest_candidate) else None

    back_path = newest("outputs\\pm10_backtest_*.csv")
    if not pred_path or not back_path:
        raise RuntimeError("Brak plików do scalenia. Sprawdź outputs\\pm10_pred_* i outputs\\pm10_backtest_*.")
    out_path = os.path.join(ROOT, "outputs", "pm10_all_latest.csv")
    # wybierz plik pogodowy (WAQI) — preferuj aqicn_slupsk_data.csv, fallback na merged_hourly
    weather_candidate = "data\\aqicn_slupsk_data.csv" if os.path.exists(os.path.join(ROOT, "data", "aqicn_slupsk_data.csv")) else "data\\merged_hourly.csv"
    run([
        sys.executable, "src\\merge_pm10_results.py",
        "--backtest", back_path,
        "--prediction", pred_path,
        "--weather", weather_candidate,
        "--time-col", "timestamp",
        "--sep", sep, "--encoding", encoding,
        "--coalesce-hist",
        "--out", out_path
    ])

    # Podsumowanie metryk (z pliku backtestu)
    back = pd.read_csv(back_path)
    mae = float((back["error"].abs().mean()))
    rmse = float((back["error"]**2).mean()**0.5)
    nonzero = back["y_true"] != 0
    mape = float((back.loc[nonzero, "error"].abs() / back.loc[nonzero, "y_true"]).mean()*100) if nonzero.any() else float("nan")
    print("\n✅ Zaktualizowano dashboard:")
    print("   plik scalony:", out_path)
    print(f"   metryki: MAE={mae:.3f}, RMSE={rmse:.3f}, MAPE={mape:.1f}%")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=24, help="Horyzont przyszłości (godziny)")
    p.add_argument("--copy-last", action="store_true", help="Skopiuj ostatnie meteo do przyszłości (zamiast NaN)")
    p.add_argument("--sep", type=str, default=",", help="Separator CSV")
    p.add_argument("--encoding", type=str, default="utf-8", help="Kodowanie CSV")
    args = p.parse_args()
    main(hours=args.hours, copy_last=args.copy_last, sep=args.sep, encoding=args.encoding)
