@echo off
REM Testy projektu na tymczasowej kopii (rownolegle). Uzycie: run_tests.bat [-n 6] [argumenty pytest]
cd /d "%~dp0" || exit /b 1
call "%~dp0ensure_env.bat" interactive || exit /b 1
".venv\Scripts\python.exe" tests\run_isolated.py %*
exit /b %ERRORLEVEL%
