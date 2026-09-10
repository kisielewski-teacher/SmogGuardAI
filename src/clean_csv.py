
# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
inp  = ROOT / "data" / "aqicn_slupsk_data.csv"
outp = ROOT / "data" / "aqicn_slupsk_data_clean.csv"

print("[INFO] Wczytuję:", inp)
df = pd.read_csv(inp, on_bad_lines="skip", engine="python")

# Daty i typy
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
num_cols = ["PM10", "PM2.5", "NO2", "O3", "temperatura", "predkosc_wiatru",
            "wilgotnosc_wzgledna", "cisnienie", "aqi", "wg"]
for c in num_cols:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

# Resampling do pełnych godzin + średnia
df_clean = (df
            .dropna(subset=["timestamp"])
            .set_index("timestamp")
            .groupby(pd.Grouper(freq="h"))
            .mean(numeric_only=True)
            .reset_index())

df_clean.to_csv(outp, index=False, encoding="utf-8")
print("[OK] Zapisano:", outp, "wierszy:", len(df_clean))
