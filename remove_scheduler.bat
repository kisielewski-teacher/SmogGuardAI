
@echo off
REM --- Harmonogram Windows wymaga uprawnien administratora: jesli ich nie ma, uruchom ten plik ponownie z UAC ---
fltmc >nul 2>&1
if errorlevel 1 (
    echo [INFO] Potrzebne uprawnienia administratora. Za chwile pojawi sie okno UAC - kliknij Tak.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
set "TASK_NAME=Powietrze_Slupsk_Hourly"
echo [INFO] Usuwanie zadania: %TASK_NAME%
schtasks /Delete /TN "%TASK_NAME%" /F
if %ERRORLEVEL% EQU 0 (
    echo [OK] Zadanie usuniete.
) else (
    echo [ERROR] Nie znaleziono zadania.
)
pause
