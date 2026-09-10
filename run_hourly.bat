
@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
setlocal

REM === USTAWIENIA PROJEKTU ===
cd /d "%~dp0" || (
  echo [ERR] Nie moge przejsc do katalogu skryptu.
  goto :end
)
set "PROJ_DIR=%CD%"
set "VENV_DIR=%PROJ_DIR%\.venv"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"
set "PIP=%VENV_DIR%\Scripts\pip.exe"

echo [INFO] PROJ_DIR=%PROJ_DIR%
echo [INFO] VENV_DIR=%VENV_DIR%
echo [INFO] PYTHON=%PYTHON%

if not exist "%VENV_DIR%\Scripts\activate.bat" (
  echo [ERR] Brak wirtualnego srodowiska w "%VENV_DIR%".
  echo Tworze srodowisko i instaluje zaleznosci...
  py -m venv ".venv" || (echo [ERR] Nie moge utworzyc .venv & goto :end)
)

call "%VENV_DIR%\Scripts\activate.bat"

REM === SPRAWDZENIE, CZY PANDAS JEST ZAINSTALOWANY ===
"%PYTHON%" -c "import pandas" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Brakuje pakietow w .venv – instalacja requirements...
  "%PYTHON%" -m pip install --upgrade pip
  "%PYTHON%" -m pip install -r "%PROJ_DIR%\requirements.txt" || (
    echo [ERR] Instalacja requirements nie powiodla sie.
    goto :end
  )
)

REM === KATALOGI WYJŚCIOWE ===
if not exist "%PROJ_DIR%\data" mkdir "%PROJ_DIR%\data"
if not exist "%PROJ_DIR%\logs" mkdir "%PROJ_DIR%\logs"

REM === PIPELINE 1: POBIERANIE ===
"%PYTHON%" "%PROJ_DIR%\src\waqi_fetch.py"
if errorlevel 1 echo [WARN] waqi_fetch.py zakonczyl sie kodem %ERRORLEVEL%

"%PYTHON%" "%PROJ_DIR%\src\imgw_fetch.py"
if errorlevel 1 echo [WARN] imgw_fetch.py zakonczyl sie kodem %ERRORLEVEL%

"%PYTHON%" "%PROJ_DIR%\src\gios_fetch.py"
if errorlevel 1 echo [WARN] gios_fetch.py zakonczyl sie kodem %ERRORLEVEL%

"%PYTHON%" "%PROJ_DIR%\src\airly_fetch.py"
if errorlevel 1 echo [WARN] airly_fetch.py zakonczyl sie kodem %ERRORLEVEL%

"%PYTHON%" "%PROJ_DIR%\src\sensor_community_fetch.py"
if errorlevel 1 echo [WARN] sensor_community_fetch.py zakonczyl sie kodem %ERRORLEVEL%

"%PYTHON%" "%PROJ_DIR%\src\merge_hourly.py"
if errorlevel 1 echo [WARN] merge_hourly.py zakonczyl sie kodem %ERRORLEVEL%
REM === PIPELINE 2: TRENING ===
"%PYTHON%" "%PROJ_DIR%\src\train_pm10.py" >> "%PROJ_DIR%\logs\train.log" 2>&1
REM "%PYTHON%" "%PROJ_DIR%\src\train_pm25.py" >> "%PROJ_DIR%\logs\train_pm25.log" 2>&1  REM tymczasowo wylaczony — tylko PM10

REM === PIPELINE 3: PREDYKCJA ===
"%PYTHON%" "%PROJ_DIR%\src\predict.py" ^
  --features "%PROJ_DIR%\data\features_pm10.csv" ^
  --model "%PROJ_DIR%\models\pm10_rf.pkl" ^
  --out "%PROJ_DIR%\outputs\pm10_pred_latest.csv" ^
  >> "%PROJ_DIR%\logs\predict.log" 2>&1

REM "%PYTHON%" "%PROJ_DIR%\src\predict_pm25.py" >> "%PROJ_DIR%\logs\predict_pm25.log" 2>&1  REM tymczasowo wylaczona — tylko PM10


"%PYTHON%" "%PROJ_DIR%\src\merge_pm10_results.py" ^
  --backtest "%PROJ_DIR%\data\aqicn_slupsk_data.csv" ^
  --prediction "%PROJ_DIR%\outputs\pm10_pred_latest.csv" ^
  --weather "%PROJ_DIR%\data\aqicn_slupsk_data.csv" ^
  --time-col timestamp ^
  --coalesce-hist ^
  --out "%PROJ_DIR%\outputs\pm10_all_latest.csv" ^
  >> "%PROJ_DIR%\logs\merge.log" 2>&1

echo [OK] Zakonczono run_hourly.bat

:end
endlocal
