import os
import sys
import shutil
import subprocess
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
OUT = REPO / "outputs"
MODELS = REPO / "models"

# files touched by the integration flow
FILES_TO_BACKUP = [
    DATA / "merged_hourly.csv",
    DATA / "gios_slupsk.csv",
    DATA / "imgw_synop_hourly.csv",
    DATA / "syngeos_agg.csv",
    DATA / "features_pm10.csv",
    DATA / "forecast_pm25.csv",
    OUT / "pm10_all_latest.csv",
    OUT / "pm10_pred_latest.csv",
    MODELS / "pm25_rf.pkl",
]


def _backup(p: Path):
    if p.exists():
        shutil.copy(p, p.with_suffix(p.suffix + ".bak"))


def _restore(p: Path):
    bak = p.with_suffix(p.suffix + ".bak")
    if bak.exists():
        if p.exists():
            p.unlink()
        shutil.move(bak, p)


def test_pipeline_minimal_end_to_end(tmp_path):
    # backup repo files we will overwrite
    for f in FILES_TO_BACKUP:
        _backup(f)

    try:
        DATA.mkdir(parents=True, exist_ok=True)
        OUT.mkdir(parents=True, exist_ok=True)
        MODELS.mkdir(parents=True, exist_ok=True)

        # 1) prepare minimal GIOŚ (backtest-like) with PM10 (no PM2.5 required)
        gios = (
            "timestamp,station,PM2.5,PM10,NO2,O3\n"
            "2026-01-01 00:00:00,Test,,10,,\n"
            "2026-01-01 01:00:00,Test,,12,,\n"
            "2026-01-01 02:00:00,Test,,11,,\n"
        )
        (DATA / "gios_slupsk.csv").write_text(gios)

        # 2) IMGW weather (matching timestamps)
        imgw = (
            "timestamp,temperatura,predkosc_wiatru,wilgotnosc_wzgledna,cisnienie\n"
            "2026-01-01 00:00:00,0.1,1.0,90,1012\n"
            "2026-01-01 01:00:00,0.2,1.2,91,1012\n"
            "2026-01-01 02:00:00,0.0,0.8,89,1011\n"
        )
        (DATA / "imgw_synop_hourly.csv").write_text(imgw)

        # 3) Syngeos aggregate with pm25_mean for at least one timestamp
        syngeos = (
            "timestamp,pm25_mean,pm25_count,pm10_mean,pm10_count\n"
            "2026-01-01 01:00:00,5.5,3,1.2,3\n"
        )
        (DATA / "syngeos_agg.csv").write_text(syngeos)

        # 4) ensure PM2.5 model is absent so predict_pm25 uses fallback
        pm25_model = MODELS / "pm25_rf.pkl"
        if pm25_model.exists():
            pm25_model.unlink()

        # 5) create a simple pm10 prediction file used by merge
        pred = (
            "timestamp,pm10_pred\n"
            "2026-01-01 01:00:00,11.5\n"
            "2026-01-01 02:00:00,10.8\n"
            "2026-01-01 03:00:00,9.9\n"
        )
        (OUT / "pm10_pred_latest.csv").write_text(pred)

        # --- run steps ---
        # merge_hourly (will read gios + imgw + syngeos aggregate)
        r = subprocess.run([sys.executable, "src/merge_hourly.py"], cwd=str(REPO), capture_output=True, text=True)
        assert r.returncode == 0, f"merge_hourly failed: {r.stderr}\n{r.stdout}"
        assert (DATA / "merged_hourly.csv").exists()

        # features
        r = subprocess.run([sys.executable, "src/features.py"], cwd=str(REPO), capture_output=True, text=True)
        assert r.returncode == 0, f"features.py failed: {r.stderr}\n{r.stdout}"
        assert (DATA / "features_pm10.csv").exists()

        # predict_pm25 (should create forecast_pm25.csv via fallback)
        r = subprocess.run([sys.executable, "src/predict_pm25.py"], cwd=str(REPO), capture_output=True, text=True)
        assert r.returncode == 0, f"predict_pm25.py failed: {r.stderr}\n{r.stdout}"
        assert (DATA / "forecast_pm25.csv").exists()

        # merge results (produce outputs/pm10_all_latest.csv)
        out_file = OUT / "pm10_all_latest_from_test.csv"
        r = subprocess.run([
            sys.executable, "src/merge_pm10_results.py",
            "--backtest", str(DATA / "gios_slupsk.csv"),
            "--prediction", str(OUT / "pm10_pred_latest.csv"),
            "--weather", str(DATA / "merged_hourly.csv"),
            "--time-col", "timestamp",
            "--coalesce-hist",
            "--out", str(out_file),
        ], cwd=str(REPO), capture_output=True, text=True)
        assert r.returncode == 0, f"merge_pm10_results.py failed: {r.stderr}\n{r.stdout}"
        assert out_file.exists()

        # PM2.5 merging into the dashboard file is intentionally disabled in
        # merge_pm10_results.py ("PM2.5 tymczasowo ukryte — tylko PM10"), consistently
        # with app/app_extended_multi.py. So pm25_pred is not expected here; instead
        # verify the PM10 columns the merge is actually responsible for.
        df = pd.read_csv(out_file)
        assert "pm25_pred" not in df.columns
        assert {"timestamp", "pm10_true", "pm10_pred", "pm10_hist", "error"}.issubset(df.columns)
        assert df["pm10_pred"].notna().any()

    finally:
        # restore backups
        for f in FILES_TO_BACKUP:
            _restore(f)
        # clean up test output file
        try:
            (OUT / "pm10_all_latest_from_test.csv").unlink()
        except Exception:
            pass
