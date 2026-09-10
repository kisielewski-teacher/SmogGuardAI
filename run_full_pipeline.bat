@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
setlocal enabledelayedexpansion

:: run_full_pipeline.bat — pełny pipeline (Windows)
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
echo [STEP] 1/10 — Fetch danych (WAQI / IMGW / Syngeos)
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
echo [STEP] 2/10 — Scalanie danych godzinowych (merge_hourly)
"%PY%" "%PROJ_DIR%\src\merge_hourly.py" --waqi "%PROJ_DIR%\data\aqicn_slupsk_data.csv" --imgw "%PROJ_DIR%\data\imgw_slupsk_hourly.csv" --out "%PROJ_DIR%\data\merged_hourly.csv" --tolerance 1h --on_bad_lines skip >>"%PROJ_DIR%\logs\merge_hourly.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] merge_hourly failed

echo.
echo [STEP] 3/10 — Budowa cech (features)
"%PY%" "%PROJ_DIR%\src\features.py" >>"%PROJ_DIR%\logs\features.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] features.py failed

echo.
echo [STEP] 4/10 — Trening modelu PM10 (pipeline)
"%PY%" "%PROJ_DIR%\src\train_pm10_rf.py" --time-col timestamp --lags 1 3 6 12 24 --rolling 3 6 12 24 --n-estimators 300 >>"%PROJ_DIR%\logs\train_pm10_rf.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] train_pm10_rf failed

echo.
REM echo [STEP] 5/10 — Trening modelu PM2.5 (tymczasowo wylaczony — tylko PM10)
REM "%PY%" "%PROJ_DIR%\src\train_pm25.py" >>"%PROJ_DIR%\logs\train_pm25.log" 2>&1

echo.
echo [STEP] 6/10 — Predykcja (PM10)
"%PY%" "%PROJ_DIR%\src\predict_pm10.py" --features "%PROJ_DIR%\data\merged_hourly.csv" --model "%PROJ_DIR%\models\pm10_pipeline.pkl" --out "%PROJ_DIR%\outputs\pm10_pred_latest.csv" --horizon 24 --align-to "%PROJ_DIR%\data\aqicn_slupsk_data.csv" --verbose >>"%PROJ_DIR%\logs\predict.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] predict_pm10 failed

echo.
REM echo [STEP] 7/10 — Predykcja (PM2.5) (tymczasowo wylaczona — tylko PM10)
REM "%PY%" "%PROJ_DIR%\src\predict_pm25.py" >>"%PROJ_DIR%\logs\predict_pm25.log" 2>&1

echo.
echo [STEP] 8/10 — Backtest historii PM10 (walk‑forward)
"%PY%" "%PROJ_DIR%\src\backtest_pm10.py" --csv-path "%PROJ_DIR%\data\merged_hourly.csv" --model "%PROJ_DIR%\models\pm10_pipeline.pkl" --out-dir "%PROJ_DIR%\outputs" >>"%PROJ_DIR%\logs\backtest.log" 2>&1
set "RC=%ERRORLEVEL%"
if %RC% neq 0 echo [WARN] backtest_pm10 failed

echo.
REM echo [STEP] 9/10 — Backtest PM2.5 (tymczasowo wylaczony — tylko PM10)
REM "%PY%" "%PROJ_DIR%\src\backtest_pm10.py" --csv-path "%PROJ_DIR%\data\merged_hourly.csv" --target PM2.5 --model "%PROJ_DIR%\models\pm25_rf.pkl" --out-dir "%PROJ_DIR%\outputs" >>"%PROJ_DIR%\logs\backtest_pm25.log" 2>&1

REM --- wybierz najnowszy plik backtest oraz predykcję ---
set "BACKTEST_FILE="
for /f "delims=" %%F in ('dir /b /a:-d /o:-d "%PROJ_DIR%\outputs\pm10_backtest_*.csv" 2^>nul') do (
  set "BACKTEST_FILE=%%F"
  goto :have_backtest
)
:have_backtest
if defined BACKTEST_FILE (
  echo [INFO] Latest backtest found: %BACKTEST_FILE%
) else (
  echo [WARN] No backtest file found (skipping merge step)
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
if defined PRED_FILE (echo [INFO] Prediction file: %PRED_FILE%) else (echo [WARN] No prediction file found)

echo.
if defined BACKTEST_FILE if defined PRED_FILE (
  echo [STEP] 10/10 — Scalanie wynikow do outputs\pm10_all_latest.csv
  "%PY%" "%PROJ_DIR%\src\merge_pm10_results.py" --backtest "%PROJ_DIR%\outputs\%BACKTEST_FILE%" --prediction "%PROJ_DIR%\outputs\%PRED_FILE%" --weather "%PROJ_DIR%\data\aqicn_slupsk_data.csv" --time-col timestamp --coalesce-hist --out "%PROJ_DIR%\outputs\pm10_all_latest.csv" >>"%PROJ_DIR%\logs\merge_results.log" 2>&1
  set "RC=%ERRORLEVEL%"
  if %RC% neq 0 echo [WARN] merge_pm10_results failed
) else (
  echo [WARN] Merge skipped (brak backtest/predykcji)
)

echo.
echo [OK] Pipeline zakonczony — sprawdz %PROJ_DIR%\outputs i %PROJ_DIR%\logs\
endlocal
exit /b 0
