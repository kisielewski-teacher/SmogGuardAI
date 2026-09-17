
@echo off
set "TASK_NAME=Powietrze_Slupsk_Hourly"
echo [INFO] Usuwanie zadania: %TASK_NAME%
schtasks /Delete /TN "%TASK_NAME%" /F
if %ERRORLEVEL% EQU 0 (
    echo [OK] Zadanie usunięte.
) else (
    echo [ERROR] Nie znaleziono zadania.
)
pause
