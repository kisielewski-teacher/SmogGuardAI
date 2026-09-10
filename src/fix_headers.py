
# src/fix_headers.py
import pandas as pd
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "data" / "merged_hourly.csv"
df = pd.read_csv(path)

# Ujednolicenie nazw (np. jeśli masz 'PM25' zamiast 'PM2.5' albo 'NO₂' zamiast 'NO2')
rename_map = {
    'PM25': 'PM2.5',
    'NO₂': 'NO2',
    'O₃': 'O3',
}
df = df.rename(columns=rename_map)

# Sprawdź brakujące kolumny i dołącz puste, jeśli chcesz ruszyć trening (niezalecane jakościowo)
for col in ['PM2.5', 'NO2', 'O3']:
    if col not in df.columns:
        print(f'[WARN] Brak {col} – dodaję pustą kolumnę (NaN). Lepiej zasilić realnymi danymi!')
        df[col] = pd.NA

df.to_csv(path, index=False)
print('[OK] Zapisano poprawiony merged_hourly.csv')
