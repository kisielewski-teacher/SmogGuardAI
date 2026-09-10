
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

src = DATA_DIR / "merged_hourly.csv"
out = DATA_DIR / "features_pm10.csv"

def main():
    df = pd.read_csv(src, parse_dates=["timestamp"], engine="python", on_bad_lines="skip") if src.exists() else pd.DataFrame()
    # Obsługa aliasów: merge_hourly może generować PM10_x zamiast PM10 po złączeniu.
    # Jeśli PM10 istnieje ale ma mniej danych niż PM10_x, użyj PM10_x.
    current_pm10_count = df["PM10"].notna().sum() if "PM10" in df.columns else 0
    for alias in ["PM10_x", "PM10_y", "pm10_mean"]:
        if alias in df.columns:
            alias_count = pd.to_numeric(df[alias], errors="coerce").notna().sum()
            if alias_count > current_pm10_count:
                df["PM10"] = pd.to_numeric(df[alias], errors="coerce")
                current_pm10_count = alias_count
    if df.empty or current_pm10_count == 0:
        raise RuntimeError("Brak danych PM10 w merged_hourly.csv")

    df["hour"] = df["timestamp"].dt.hour
    df["weekday"] = df["timestamp"].dt.weekday
    df["month"] = df["timestamp"].dt.month
    df["heating"] = df["month"].isin([11,12,1,2,3]).astype(int)

    df["PM10_lag1"] = df["PM10"].shift(1)
    df["PM10_lag2"] = df["PM10"].shift(2)
    df["PM10_lag3"] = df["PM10"].shift(3)
    df["PM10_roll3"] = df["PM10"].rolling(3).mean().shift(1)

    # Obsługa aliasów pogodowych z sufiksami _x/_y po złączeniu
    for base_col, aliases in [
        ("temperatura", ["temperatura_x", "temperatura_y"]),
        ("predkosc_wiatru", ["predkosc_wiatru_x", "predkosc_wiatru_y"]),
        ("wilgotnosc_wzgledna", ["wilgotnosc_wzgledna_x", "wilgotnosc_wzgledna_y"]),
        ("cisnienie", ["cisnienie_x", "cisnienie_y"]),
    ]:
        if base_col not in df.columns:
            for alias in aliases:
                if alias in df.columns:
                    df[base_col] = pd.to_numeric(df[alias], errors="coerce")
                    break
    # suma_opadu często jest NaN (brak pomiaru = brak opadów), wypełnij 0
    if "suma_opadu" in df.columns:
        df["suma_opadu"] = df["suma_opadu"].fillna(0.0)
    weather_cols = [c for c in ["temperatura","predkosc_wiatru","wilgotnosc_wzgledna","suma_opadu","cisnienie"] if c in df.columns]
    feat_cols = ["hour","weekday","month","heating","PM10_lag1","PM10_lag2","PM10_lag3","PM10_roll3"] + weather_cols

    # Wymagane kolumny: PM10 i lagi (pogoda opcjonalna — już uzupełniona)
    required_cols = ["timestamp", "PM10", "PM10_lag1", "PM10_lag3", "PM10_roll3"]
    out_df = df[["timestamp","PM10"] + feat_cols].dropna(subset=required_cols)
    out_df.to_csv(out, index=False)
    print(f"Zapisano cechy do {out}")

if __name__ == "__main__":
    main()
