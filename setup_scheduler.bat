
@echo off
:: ===========================================
:: Ustawienie Harmonogramu dla run_pipeline_scheduled.bat
:: (fetch + merge + trening + predykcja 72h + backtest + merge wynikow;
::  BEZ uruchamiania dashboardu — ten trzymaj włączony osobno)
:: ===========================================

set "TASK_NAME=Powietrze_Slupsk_Hourly"
set "BAT_PATH=%~dp0run_pipeline_scheduled.bat"

echo [INFO] Tworzenie zadania Harmonogramu: %TASK_NAME%
echo [INFO] Plik BAT: %BAT_PATH%

:: Sprawdź, czy plik istnieje
if not exist "%BAT_PATH%" (
    echo [ERROR] Nie znaleziono pliku: %BAT_PATH%
    pause
    exit /b 1
)

:: Utwórz zadanie co godzinę, uruchamiane jako bieżący użytkownik
schtasks /Create /TN "%TASK_NAME%" /SC HOURLY /MO 1 /ST 00:00 /TR "\"%BAT_PATH%\"" /F

if %ERRORLEVEL% EQU 0 (
    echo [OK] Zadanie zostało utworzone pomyślnie!
    echo [INFO] Testowe uruchomienie zadania...
    schtasks /Run /TN "%TASK_NAME%"
    echo [INFO] Zadanie uruchomione. Sprawdź logi w folderze logs\.
) else (
    echo [ERROR] Wystąpił problem podczas tworzenia zadania.
)

pause
