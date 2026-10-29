@echo off
:: ensure_env.bat - wspolne sprawdzenie srodowiska przed uruchomieniem projektu.
:: 1) Python 3.10+ (jak brak: instalacja przez winget albo instrukcja reczna)
:: 2) .venv (jak brak: tworzy)
:: 3) pakiety z requirements.txt (jak brakuje: instaluje)
:: Uzycie: call ensure_env.bat [interactive]   (interactive = na bledzie czeka na klawisz)
:: Zwraca kod 0 gdy wszystko gotowe, 1 gdy sie nie udalo.
setlocal
set "ENV_DIR=%~dp0"
if "%ENV_DIR:~-1%"=="\" set "ENV_DIR=%ENV_DIR:~0,-1%"
set "ENV_VENV=%ENV_DIR%\.venv"
set "ENV_PY=%ENV_VENV%\Scripts\python.exe"
set "ENV_REQ=%ENV_DIR%\requirements.txt"
set "ENV_INTERACTIVE=%~1"

if not exist "%ENV_REQ%" (
  echo [ERR] Brak pliku requirements.txt w %ENV_DIR%
  goto :fail
)

REM --- 1) Python (potrzebny tylko gdy nie ma .venv) ---
if exist "%ENV_PY%" goto :have_venv
set "PYCMD="
call :find_python
if defined PYCMD goto :create_venv

echo [WARN] Nie znaleziono Pythona 3.10 lub nowszego.
where winget >nul 2>&1
if errorlevel 1 (
  echo [ERR] Zainstaluj Pythona 3.10+ recznie: https://www.python.org/downloads/
  echo [ERR] Zaznacz "Add Python to PATH", a potem uruchom ten plik ponownie.
  goto :fail
)
echo [INFO] Instaluje Pythona 3.12 przez winget (tylko dla biezacego uzytkownika)...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%ProgramFiles%\Python312\python.exe") do (
  if not defined PYCMD if exist %%P set "PYCMD=%%~P"
)
if not defined PYCMD (
  echo [ERR] Instalacja Pythona sie nie powiodla. Zainstaluj recznie: https://www.python.org/downloads/
  goto :fail
)
echo [OK] Python zainstalowany: %PYCMD%

REM --- 2) .venv ---
:create_venv
echo [INFO] Brak .venv - tworze srodowisko wirtualne...
%PYCMD% -m venv "%ENV_VENV%"
if errorlevel 1 (
  echo [ERR] Nie udalo sie utworzyc .venv
  goto :fail
)

REM --- 3) Pakiety ---
:have_venv
"%ENV_PY%" -c "import requests,pandas,numpy,matplotlib,seaborn,sklearn,dateutil,dotenv,streamlit,plotly,joblib,bs4,pytest,xdist,lightgbm" >nul 2>&1
if not errorlevel 1 goto :ok
echo [INFO] Brakuje pakietow w .venv - instaluje z requirements.txt...
"%ENV_PY%" -m pip install --upgrade pip >nul 2>&1
"%ENV_PY%" -m pip install -r "%ENV_REQ%"
if errorlevel 1 (
  echo [ERR] Instalacja wymaganych pakietow sie nie powiodla.
  goto :fail
)
"%ENV_PY%" -c "import requests,pandas,numpy,matplotlib,seaborn,sklearn,dateutil,dotenv,streamlit,plotly,joblib,bs4,pytest,xdist,lightgbm" >nul 2>&1
if errorlevel 1 (
  echo [ERR] Po instalacji nadal brakuje pakietow - sprawdz requirements.txt i polaczenie z internetem.
  goto :fail
)
echo [OK] Pakiety zainstalowane.

:ok
echo [OK] Srodowisko gotowe.
endlocal & exit /b 0

:fail
if /i "%ENV_INTERACTIVE%"=="interactive" pause
endlocal & exit /b 1

:find_python
for %%C in ("py -3" "python") do (
  if not defined PYCMD (
    %%~C -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
    if not errorlevel 1 set "PYCMD=%%~C"
  )
)
exit /b 0
