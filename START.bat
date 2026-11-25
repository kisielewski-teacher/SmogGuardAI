@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0" || exit /b 1
echo === SmogGuardAI: sprawdzanie srodowiska (pierwsze uruchomienie trwa kilka minut) ===
call "%~dp0ensure_env.bat" interactive || exit /b 1
if not exist logs mkdir logs
echo [INFO] Panel otworzy sie w przegladarce (http://localhost:8501). Zamkniecie: Ctrl+C w tym oknie.
".venv\Scripts\python.exe" -m streamlit run app\app_extended_multi.py
pause
