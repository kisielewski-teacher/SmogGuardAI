@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0" || exit /b 1
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist logs mkdir logs

REM Szybkie odswiezenie prognozy (bez treningu): swieze dane -> predykcja 72 h -> plik dla panelu.
echo [INFO] Odswiezanie prognozy (potrzebny internet, ok. 1-3 minut)...
"%PY%" src\gios_fetch.py >>logs\fetch.log 2>&1
if errorlevel 1 echo [WARN] Nie pobrano swiezych pomiarow GIOS (uzywam danych zapisanych na dysku).
"%PY%" src\imgw_fetch.py >>logs\fetch.log 2>&1
if errorlevel 1 echo [WARN] Nie pobrano swiezej pogody IMGW (uzywam danych zapisanych na dysku).
"%PY%" src\merge_hourly.py >>logs\merge_hourly.log 2>&1
if errorlevel 1 echo [WARN] merge_hourly nie powiodl sie & exit /b 1

"%PY%" src\predict_pm10.py --features data\merged_hourly.csv --model models\pm10_pipeline.pkl --out outputs\pm10_pred_latest.csv --horizon 72 --align-to data\gios_slupsk.csv >>logs\predict.log 2>&1
if errorlevel 1 echo [WARN] predict_pm10 nie powiodl sie (patrz logs\predict.log) & exit /b 1
"%PY%" src\direct_forecast.py predict >>logs\direct_forecast.log 2>&1
if errorlevel 1 echo [WARN] direct_forecast nie powiodl sie (zostaje prognoza rekurencyjna)

set "BT="
for /f "delims=" %%F in ('dir /b /a:-d /o:-d outputs\pm10_backtest_*.csv 2^>nul') do (
  set "BT=%%F"
  goto :have_bt
)
:have_bt
if not defined BT echo [WARN] Brak pliku backtestu, nie scalam wynikow & exit /b 1
"%PY%" src\merge_pm10_results.py --pollutant pm10 --backtest "outputs\%BT%" --prediction outputs\pm10_pred_latest.csv --weather data\merged_hourly.csv --time-col timestamp --coalesce-hist --out outputs\pm10_all_latest.csv >>logs\merge_results.log 2>&1
if errorlevel 1 echo [WARN] merge_pm10_results nie powiodl sie (patrz logs\merge_results.log) & exit /b 1
echo [OK] Prognoza odswiezona.
exit /b 0
