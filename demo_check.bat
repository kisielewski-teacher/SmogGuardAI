@echo off
REM Kontrola gotowosci przed prezentacja (dane, prognoza, modele, panel, internet).
cd /d "%~dp0" || exit /b 1
call "%~dp0ensure_env.bat" interactive || exit /b 1
".venv\Scripts\python.exe" src\demo_check.py
set RC=%ERRORLEVEL%
pause
exit /b %RC%
