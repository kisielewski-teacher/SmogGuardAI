@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0" || exit /b 1
echo === SmogGuardAI: sprawdzanie srodowiska (pierwsze uruchomienie trwa kilka minut) ===
call "%~dp0ensure_env.bat" interactive || exit /b 1
if not exist logs mkdir logs
REM Prognoza starsza niz 6 godzin (albo jej brak) -> odswiez przed startem panelu
powershell -NoProfile -Command "if ((Test-Path 'outputs\pm10_all_latest.csv') -and (((Get-Date)-(Get-Item 'outputs\pm10_all_latest.csv').LastWriteTime).TotalHours -lt 6)) { exit 0 } else { exit 1 }"
if errorlevel 1 call "%~dp0odswiez_prognoze.bat"
echo [INFO] Panel otworzy sie w przegladarce (http://localhost:8501). Zamkniecie: Ctrl+C w tym oknie.
".venv\Scripts\python.exe" -m streamlit run app\app_extended_multi.py
pause
