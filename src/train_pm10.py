
from pathlib import Path
import logging
from datetime import datetime
import sys
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
import joblib  # pip install joblib

# ------------------------------------------------------------------------------
# Import wspólnych ścieżek: DATA_DIR, MERGED_HOURLY_CSV
# (pozwala ładować dane z jednego katalogu dla wszystkich skryptów/aplikacji)
# ------------------------------------------------------------------------------
# train_pm10.py jest w <ROOT>/src → dodaj ROOT do PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parent.parent))
from data_paths import DATA_DIR, MERGED_HOURLY_CSV  # wspólne ścieżki danych

# Katalogi na modele i logi (w ROOT)
BASE_DIR = Path(__file__).resolve().parents[1]
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"
MODELS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

log_path = LOGS_DIR / f"train_{datetime.now():%Y%m%d}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger("train")

# Wspólny plik cech + ścieżki wyjściowe
FEATURES_PM10_CSV = DATA_DIR / "features_pm10.csv"
MODEL_PATH = MODELS_DIR / "pm10_rf.pkl"
REPORT_PATH = LOGS_DIR / "model_report.txt"


# ------------------------------------------------------------------------------
# Helper: generator cech, gdy plik features_pm10.csv nie istnieje albo jest pusty
# ------------------------------------------------------------------------------
def ensure_features_exist() -> Path:
    """
    Gwarantuje istnienie FEATURES_PM10_CSV. Jeśli brak lub pusty,
    buduje podstawowe cechy z MERGED_HOURLY_CSV:
      - pm10_true -> kolumna docelowa 'PM10'
      - cechy czasowe: hour, dow
      - lag/rolling: pm10_lag1, pm10_lag3, pm10_roll3, pm10_roll6
      - opcjonalne cechy pogodowe, jeśli są w merged_hourly.csv
    """
    try:
        if FEATURES_PM10_CSV.exists():
            df_test = pd.read_csv(FEATURES_PM10_CSV)
            if len(df_test) > 0 and "PM10" in df_test.columns and "timestamp" in df_test.columns:
                logger.info(f"[OK] Istniejące cechy: {FEATURES_PM10_CSV} (wierszy: {len(df_test)})")
                return FEATURES_PM10_CSV
            else:
                logger.warning("[WARN] Istniejący features_pm10.csv jest pusty lub bez wymaganych kolumn – wygeneruję od nowa.")
    except Exception as e:
        logger.warning(f"[WARN] Nie udało się odczytać istniejących cech: {e}. Wygeneruję od nowa.")

    # Źródło cech: scalone dane godzinowe
    if not MERGED_HOURLY_CSV.exists():
        raise FileNotFoundError(f"Brak pliku źródłowego: {MERGED_HOURLY_CSV}")

    dfm = pd.read_csv(MERGED_HOURLY_CSV)
    if "timestamp" not in dfm.columns:
        raise RuntimeError("merged_hourly.csv nie ma kolumny 'timestamp' – nie da się zbudować cech.")
    dfm["timestamp"] = pd.to_datetime(dfm["timestamp"], errors="coerce")
    dfm = dfm.dropna(subset=["timestamp"]).sort_values("timestamp")

    # Upewnij się, że mamy kolumnę 'PM10'.
    # Jeśli brak bezpośredniej kolumny, spróbuj znaleźć alternatywy (np. PM10_x / PM10_y) i skopiować pierwszą niepustą.
    if "PM10" not in dfm.columns or dfm["PM10"].isna().all():
        alt_cols = [c for c in dfm.columns if c.upper().startswith("PM10") and c != "PM10"]
        taken = None
        for c in alt_cols:
            if dfm[c].notna().any():
                dfm["PM10"] = pd.to_numeric(dfm[c], errors="coerce")
                taken = c
                break
        if taken is None and ("PM10" not in dfm.columns or dfm["PM10"].isna().all()):
            raise RuntimeError("Brak kolumny 'PM10' (ani alternatyw PM10_x/PM10_y) w merged_hourly.csv – nie da się zbudować cech.")
        if taken:
            logger.info(f"Zastąpiono brakującą kolumnę 'PM10' danymi z: {taken}")

    # Bazowa kolumna celu
    dfm["PM10"] = pd.to_numeric(dfm["PM10"], errors="coerce")

    # Cechy czasowe
    dfm["hour"] = dfm["timestamp"].dt.hour
    dfm["dow"] = dfm["timestamp"].dt.day_of_week

    # Lagi i rolling (proste, odporne na małe zbiory)
    dfm["pm10_lag1"] = dfm["PM10"].shift(1)
    dfm["pm10_lag3"] = dfm["PM10"].shift(3)
    dfm["pm10_roll3"] = dfm["PM10"].rolling(3).mean().shift(1)
    dfm["pm10_roll6"] = dfm["PM10"].rolling(6).mean().shift(1)

    # Pogoda – jeśli dostępna, zrzucamy do float
    weather_cols_all = ["temperatura", "predkosc_wiatru", "wilgotnosc_wzgledna", "suma_opadu", "cisnienie"]
    for c in weather_cols_all:
        if c in dfm.columns:
            dfm[c] = pd.to_numeric(dfm[c], errors="coerce")

    # Minimalny zestaw wymagany do startu: timestamp + PM10 + (przynajmniej jeden lag/rolling)
    df_feat = dfm.dropna(subset=["pm10_lag1", "pm10_roll3"]).copy()

    if df_feat.empty:
        raise RuntimeError("Po zbudowaniu cech nie pozostały żadne wiersze (zbyt mało danych lub same NaN). Dodaj więcej historii do merged_hourly.csv.")

    FEATURES_PM10_CSV.parent.mkdir(parents=True, exist_ok=True)
    df_feat.to_csv(FEATURES_PM10_CSV, index=False)
    logger.info(f"[INFO] Wygenerowano cechy: {FEATURES_PM10_CSV} (wierszy: {len(df_feat)})")
    return FEATURES_PM10_CSV


# ------------------------------------------------------------------------------
# Trening modelu
# ------------------------------------------------------------------------------
def main():
    # Zapewnij cechy
    features_path = ensure_features_exist()

    # Wczytaj cechy
    df = pd.read_csv(features_path, parse_dates=["timestamp"])
    if df.empty:
        raise RuntimeError("Plik features_pm10.csv jest pusty – brak danych do trenowania.")

    # Walidacja minimalnych kolumn
    required_cols = {"PM10", "timestamp"}
    if not required_cols.issubset(set(df.columns)):
        raise RuntimeError(f"Brak wymaganych kolumn w cechach: {required_cols}. Dostępne: {list(df.columns)}")

    # Target i cechy
    y = df["PM10"].astype(float)
    X = df.drop(columns=["PM10", "timestamp"])

    # Usuń kolumny nienumeryczne (np. nazwy stacji), zostaw tylko cechy liczbowe
    non_numeric = X.select_dtypes(exclude=["number"]).columns.tolist()
    if non_numeric:
        logger.warning(f"Usuwam kolumny nienumeryczne przed treningiem: {non_numeric}")
        X = X.select_dtypes(include=["number"]).copy()

    # Walidacja: przynajmniej kilka kolumn cech
    if X.shape[1] == 0:
        raise RuntimeError("Brak kolumn cech po odrzuceniu 'PM10' i 'timestamp' (wszystkie kolumny były nienumeryczne).")

    # Walidacja czasowa
    ts = TimeSeriesSplit(n_splits=4)
    scores = []
    for tr_idx, te_idx in ts.split(X):
        m = RandomForestRegressor(n_estimators=300, random_state=42, n_jobs=-1)
        m.fit(X.iloc[tr_idx], y.iloc[tr_idx])
        pred = m.predict(X.iloc[te_idx])
        rmse = float(np.sqrt(mean_squared_error(y.iloc[te_idx], pred)))
        scores.append(rmse)
    rmse_avg = float(np.mean(scores))
    logger.info(f"Średni RMSE (TimeSeriesSplit): {rmse_avg:.2f}")

    # Trening na całości i zapis modelu
    model = RandomForestRegressor(n_estimators=300, random_state=42, n_jobs=-1)
    model.fit(X, y)
    joblib.dump(model, MODEL_PATH)
    logger.info(f"Zapisano model do {MODEL_PATH}")

    # Raport
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(f"RMSE (TimeSeriesSplit): {rmse_avg:.3f}\n")
        f.write(f"Liczba próbek: {len(df)}\n")
        f.write(f"Cechy: {list(X.columns)}\n")
    logger.info(f"Raport zapisany: {REPORT_PATH}")


if __name__ == "__main__":
    main()
