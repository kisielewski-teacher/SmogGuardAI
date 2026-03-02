# SmogGuardAI — Instrukcja Obsługi

## 📌 Wymagania
- Python 3.10+
- Wirtualne środowisko (`.venv`)
- Pakiety: `pandas`, `numpy`, `scikit-learn`, `streamlit`, `plotly`, `joblib`, `requests`

Instalacja:
```bash
pip install -r requirements.txt
```

---

## 📂 Struktura katalogów
```
air3/
 ├─ data/                # dane źródłowe i scalone
 ├─ outputs/             # modele, prognozy, backtest, pm10_all_latest.csv
 ├─ src/                 # skrypty pipeline'u
 ├─ app/                 # dashboardy Streamlit
 └─ .venv/               # środowisko wirtualne
```

---

## ✅ Kroki uruchomienia

### 1. Pobranie danych źródłowych
```bash
py src/waqi_fetch.py --city Slupsk --out data/aqicn_slupsk_data.csv
py src/imgw_fetch.py --station <ID_STACJI> --out data/imgw_slupsk_hourly.csv
```

### 2. Scalanie danych godzinowych
```bash
py src/merge_hourly.py   --waqi data/aqicn_slupsk_data.csv   --imgw data/imgw_slupsk_hourly.csv   --out data/merged_hourly.csv   --tolerance 1h --on_bad_lines skip
```

### 3. Budowa cech (features)
```bash
py src/features.py   --in data/merged_hourly.csv   --out data/feature_table.csv   --target pm10   --lags 1 3 6 12 24 --rolling_win 6 12 24
```

### 4. Trening modelu
```bash
py src/train.py   --in data/feature_table.csv   --model outputs/pm10_model.joblib   --target pm10
```

### 5. Predykcja (24–48h)
```bash
py src/predict.py   --features data/feature_table.csv   --model outputs/pm10_model.joblib   --out outputs/pm10_pred_latest.csv
```

### 6. Backtest (opcjonalnie)
```bash
py src/backtest.py   --features data/feature_table.csv   --model outputs/pm10_model.joblib   --out outputs/pm10_backtest_latest.csv
```

### 7. Scalanie wyników do dashboardu
```bash
py src/merge_pm10_results.py   --backtest "outputs/pm10_backtest_*.csv"   --prediction "outputs/pm10_pred_*.csv"   --time-col timestamp   --coalesce-hist   --out outputs/pm10_all_latest.csv
```

### 8. Uruchomienie dashboardu
- Pełny dashboard z metrykami i eksportem:
```bash
py -m streamlit run app/app_extended_multi.py
```
- Prosty dashboard:
```bash
py -m streamlit run src/streamlit_pm10_dashboard.py
```

---

## 🔄 Automatyzacja (harmonogram)
Dodaj do crona lub Harmonogramu zadań:
```bash
# co godzinę:
py src/waqi_fetch.py ...
py src/imgw_fetch.py ...
py src/merge_hourly.py ...
py src/features.py ...
py src/predict.py ...
py src/merge_pm10_results.py ...
```

---

## ℹ️ Uwagi
- Upewnij się, że wszystkie ścieżki są poprawne (zalecane slashe `/`).
- Plik `outputs/pm10_all_latest.csv` jest źródłem danych dla dashboardu.
- Minimalna liczba wierszy do treningu: **72**.

