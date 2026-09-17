@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
setlocal enabledelayedexpansion

:: run_full_pipeline.bat — pełny pipeline (Windows), PM10 + PM2.5
:: Uruchom z katalogu projektu: .\run_full_pipeline.bat

REM --- Ustal katalog projektu i interpreter ---
cd /d "%~dp0" || (echo [ERR] Nie moge przejsc do katalogu skryptu & exit /b 1)
set "PROJ_DIR=%CD%"
set "VENV_DIR=%PROJ_DIR%\.venv"
set "PY=%VENV_DIR%\Scripts\python.exe"
set "ACTIVATE=%VENV_DIR%\Scripts\activate.bat"

echo [INFO] Project dir: %PROJ_DIR%

REM --- Utwórz / aktywuj virtualenv, zainstaluj deps jeśli trzeba ---
if not exist "%ACTIVATE%" (
  echo [INFO] Brak .venv — tworze i instaluję wymagania...
  py -3 -m venv "%VENV_DIR%" || (echo [ERR] Nie udalo sie utworzyc .venv & exit /b 1)
  call "%ACTIVATE%"
  "%PY%" -m pip install --upgrade pip >nul 2>&1
  "%PY%" -m pip install -r "%PROJ_DIR%\requirements.txt" || (echo [ERR] Instalacja wymaganych pakietow sie nie powiodla & exit /b 1)
) else (
  call "%ACTIVATE%"
)

if not exist "%PROJ_DIR%\logs" mkdir "%PROJ_DIR%\logs"
if not exist "%PROJ_DIR%\data" mkdir "%PROJ_DIR%\data"
if not exist "%PROJ_DIR%\outputs" mkdir "%PROJ_DIR%\outputs"

REM ==================== ETAPY PIPELINE ====================
echo.
echo [STEP] 1/13 — Fetch danych (WAQI / IMGW / Syngeos)
"%PY%" "%PROJ_DIR%\src\waqi_fetch.py" --city Slupsk --out "%PROJ_DIR%\data\aqicn_slupsk_data.csv" >>"%PROJ_DIR%\logs\fetch.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] waqi_fetch failed
"%PY%" "%PROJ_DIR%\src\imgw_fetch.py" >>"%PROJ_DIR%\logs\fetch.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] imgw_fetch failed
"%PY%" "%PROJ_DIR%\src\syngeos_fetch.py" --devices 411,189,623 --out "%PROJ_DIR%\data\syngeos_all.csv" --aggregate "%PROJ_DIR%\data\syngeos_agg.csv" --resample H --verbose >>"%PROJ_DIR%\logs\fetch.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] syngeos_fetch failed

echo.
echo [STEP] 2/13 — Scalanie danych godzinowych (merge_hourly)
"%PY%" "%PROJ_DIR%\src\merge_hourly.py" --waqi "%PROJ_DIR%\data\aqicn_slupsk_data.csv" --imgw "%PROJ_DIR%\data\imgw_slupsk_hourly.csv" --out "%PROJ_DIR%\data\merged_hourly.csv" --tolerance 1h --on_bad_lines skip >>"%PROJ_DIR%\logs\merge_hourly.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] merge_hourly failed

echo.
echo [STEP] 3/13 — Budowa cech (features)
"%PY%" "%PROJ_DIR%\src\features.py" >>"%PROJ_DIR%\logs\features.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] features.py failed

echo.
echo [STEP] 4/14 — Trening modelu PM10 (pipeline)
"%PY%" "%PROJ_DIR%\src\train_pm10_rf.py" --time-col timestamp --lags 1 3 6 12 24 --rolling 3 6 12 24 --n-estimators 300 >>"%PROJ_DIR%\logs\train_pm10_rf.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] train_pm10_rf failed

echo.
echo [STEP] 5/14 — Przygotowanie danych PM2.5 (realne, a gdy za malo - estymacja z PM10 + sezon)
"%PY%" "%PROJ_DIR%\src\estimate_pm25_from_pm10.py" >>"%PROJ_DIR%\logs\estimate_pm25.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] estimate_pm25_from_pm10 failed

echo.
echo [STEP] 6/14 — Trening modelu PM2.5 (ta sama architektura co PM10)
"%PY%" "%PROJ_DIR%\src\train_pm10_rf.py" --csv-path "%PROJ_DIR%\data\merged_hourly_pm25_bootstrap.csv" --target PM2.5 --time-col timestamp --lags 1 3 6 12 24 --rolling 3 6 12 24 --n-estimators 300 --model-out "%PROJ_DIR%\models\pm25_pipeline.pkl" >>"%PROJ_DIR%\logs\train_pm25_rf.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] train_pm25_rf failed (albo za malo danych — patrz logs\train_pm25_rf.log)

echo.
echo [STEP] 7/14 — Predykcja PM10 (horyzont 72h)
"%PY%" "%PROJ_DIR%\src\predict_pm10.py" --features "%PROJ_DIR%\data\merged_hourly.csv" --model "%PROJ_DIR%\models\pm10_pipeline.pkl" --out "%PROJ_DIR%\outputs\pm10_pred_latest.csv" --horizon 72 --align-to "%PROJ_DIR%\data\aqicn_slupsk_data.csv" --verbose >>"%PROJ_DIR%\logs\predict.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] predict_pm10 failed

echo.
echo [STEP] 8/14 — Predykcja PM2.5 (horyzont 72h; pomijana dopoki nie ma modelu)
"%PY%" "%PROJ_DIR%\src\predict_pm10.py" --features "%PROJ_DIR%\data\merged_hourly_pm25_bootstrap.csv" --model "%PROJ_DIR%\models\pm25_pipeline.pkl" --out "%PROJ_DIR%\outputs\pm25_pred_latest.csv" --horizon 72 --align-to "%PROJ_DIR%\data\merged_hourly_pm25_bootstrap.csv" --verbose >>"%PROJ_DIR%\logs\predict_pm25.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] predict_pm25 failed (albo brak modelu — patrz logs\predict_pm25.log)

echo.
echo [STEP] 9/14 — Backtest historii PM10 (walk-forward)
"%PY%" "%PROJ_DIR%\src\backtest_pm10.py" --csv-path "%PROJ_DIR%\data\merged_hourly.csv" --model "%PROJ_DIR%\models\pm10_pipeline.pkl" --out-dir "%PROJ_DIR%\outputs" >>"%PROJ_DIR%\logs\backtest.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] backtest_pm10 failed

echo.
echo [STEP] 10/14 — Backtest historii PM2.5 (walk-forward; pomijany dopoki nie ma modelu)
"%PY%" "%PROJ_DIR%\src\backtest_pm10.py" --csv-path "%PROJ_DIR%\data\merged_hourly_pm25_bootstrap.csv" --target PM2.5 --model "%PROJ_DIR%\models\pm25_pipeline.pkl" --out-dir "%PROJ_DIR%\outputs" >>"%PROJ_DIR%\logs\backtest_pm25.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] backtest_pm25 failed (albo brak modelu — patrz logs\backtest_pm25.log)

REM --- wybierz najnowsze pliki backtest/predykcja dla PM10 ---
set "BACKTEST_FILE="
for /f "delims=" %%F in ('dir /b /a:-d /o:-d "%PROJ_DIR%\outputs\pm10_backtest_*.csv" 2^>nul') do (
  set "BACKTEST_FILE=%%F"
  goto :have_backtest
)
:have_backtest
if defined BACKTEST_FILE (
  echo [INFO] Latest PM10 backtest found: %BACKTEST_FILE%
) else (
  echo [WARN] No PM10 backtest file found (skipping merge step)
)

set "PRED_FILE="
for /f "delims=" %%P in ('dir /b /a:-d /o:-d "%PROJ_DIR%\outputs\pm10_pred_*.csv" 2^>nul') do (
  set "PRED_FILE=%%P"
  goto :have_pred
)
:have_pred
if not defined PRED_FILE (
  if exist "%PROJ_DIR%\outputs\pm10_pred_latest.csv" set "PRED_FILE=pm10_pred_latest.csv"
)
if defined PRED_FILE (echo [INFO] PM10 prediction file: %PRED_FILE%) else (echo [WARN] No PM10 prediction file found)

echo.
if defined BACKTEST_FILE if defined PRED_FILE (
  echo [STEP] 11/14 — Scalanie wynikow PM10 do outputs\pm10_all_latest.csv
  "%PY%" "%PROJ_DIR%\src\merge_pm10_results.py" --pollutant pm10 --backtest "%PROJ_DIR%\outputs\%BACKTEST_FILE%" --prediction "%PROJ_DIR%\outputs\%PRED_FILE%" --weather "%PROJ_DIR%\data\aqicn_slupsk_data.csv" --time-col timestamp --coalesce-hist --out "%PROJ_DIR%\outputs\pm10_all_latest.csv" >>"%PROJ_DIR%\logs\merge_results.log" 2>&1
  set "RC=%ERRORLEVEL%"
  if %RC% neq 0 echo [WARN] merge_pm10_results failed
) else (
  echo [WARN] PM10 merge skipped (brak backtest/predykcji)
)

REM --- wybierz najnowsze pliki backtest/predykcja dla PM2.5 ---
set "BACKTEST25_FILE="
for /f "delims=" %%F in ('dir /b /a:-d /o:-d "%PROJ_DIR%\outputs\pm25_backtest_*.csv" 2^>nul') do (
  set "BACKTEST25_FILE=%%F"
  goto :have_backtest25
)
:have_backtest25
if defined BACKTEST25_FILE (
  echo [INFO] Latest PM2.5 backtest found: %BACKTEST25_FILE%
) else (
  echo [WARN] No PM2.5 backtest file found yet (za malo danych — to normalne na starcie)
)

set "PRED25_FILE="
if exist "%PROJ_DIR%\outputs\pm25_pred_latest.csv" set "PRED25_FILE=pm25_pred_latest.csv"
if defined PRED25_FILE (echo [INFO] PM2.5 prediction file: %PRED25_FILE%) else (echo [WARN] No PM2.5 prediction file found yet)

echo.
if defined BACKTEST25_FILE if defined PRED25_FILE (
  echo [STEP] 12/14 — Scalanie wynikow PM2.5 do outputs\pm25_all_latest.csv
  "%PY%" "%PROJ_DIR%\src\merge_pm10_results.py" --pollutant pm25 --backtest "%PROJ_DIR%\outputs\%BACKTEST25_FILE%" --prediction "%PROJ_DIR%\outputs\%PRED25_FILE%" --weather "%PROJ_DIR%\data\merged_hourly_pm25_bootstrap.csv" --time-col timestamp --coalesce-hist --out "%PROJ_DIR%\outputs\pm25_all_latest.csv" >>"%PROJ_DIR%\logs\merge_results_pm25.log" 2>&1
  set "RC=%ERRORLEVEL%"
  if %RC% neq 0 echo [WARN] merge_pm25_results failed
) else (
  echo [WARN] PM2.5 merge skipped (za malo danych jeszcze — dashboard pokaze komunikat "zbieramy dane")
)

echo.
echo [STEP] 13/14 — Audyt dokladnosci PM10 w funkcji horyzontu (h=1..72h; wolny krok, tylko przy pelnym/recznym uruchomieniu)
"%PY%" "%PROJ_DIR%\src\backtest_horizon.py" --csv-path "%PROJ_DIR%\data\merged_hourly.csv" --model "%PROJ_DIR%\models\pm10_pipeline.pkl" --target PM10 --max-horizon 72 --step-hours 48 --out "%PROJ_DIR%\outputs\pm10_horizon_accuracy.csv" >>"%PROJ_DIR%\logs\backtest_horizon.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] backtest_horizon (PM10) failed

echo.
echo [OK] Pipeline zakonczony — sprawdz %PROJ_DIR%\outputs i %PROJ_DIR%\logs\

echo.
echo [STEP] 14/14 — Uruchomienie panelu wizualizacji (dashboard)
echo [INFO] Panel otworzy sie automatycznie w przegladarce (http://localhost:8501).
echo [INFO] Aby zamknac panel, wrocz do tego okna i nacisnij Ctrl+C.
"%PY%" -m streamlit run "%PROJ_DIR%\app\app_extended_multi.py"

endlocal
exit /b 0
