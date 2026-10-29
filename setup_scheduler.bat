
@echo off
REM --- Harmonogram Windows wymaga uprawnien administratora: jesli ich nie ma, uruchom ten plik ponownie z UAC ---
fltmc >nul 2>&1
if errorlevel 1 (
    echo [INFO] Potrzebne uprawnienia administratora. Za chwile pojawi sie okno UAC - kliknij Tak.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
:: ===========================================
:: Ustawienie Harmonogramu dla run_pipeline_scheduled.bat
:: (fetch + merge + trening + predykcja 72h + backtest + merge wynikow;
::  BEZ uruchamiania dashboardu - ten trzymaj wlaczony osobno)
:: ===========================================

set "TASK_NAME=Powietrze_Slupsk_Hourly"
set "BAT_PATH=%~dp0run_pipeline_scheduled.bat"

echo [INFO] Tworzenie zadania Harmonogramu: %TASK_NAME%
echo [INFO] Plik BAT: %BAT_PATH%

:: Sprawdz, czy plik istnieje
if not exist "%BAT_PATH%" (
    echo [ERROR] Nie znaleziono pliku: %BAT_PATH%
    pause
    exit /b 1
)

:: Utworz zadanie co godzine, uruchamiane jako biezacy uzytkownik
schtasks /Create /TN "%TASK_NAME%" /SC HOURLY /MO 1 /ST 00:00 /TR "\"%BAT_PATH%\"" /F

if %ERRORLEVEL% EQU 0 (
    echo [OK] Zadanie zostalo utworzone pomyslnie!
    echo [INFO] Testowe uruchomienie zadania...
    schtasks /Run /TN "%TASK_NAME%"
    echo [INFO] Zadanie uruchomione. Sprawdz logi w folderze logs\.
) else (
    echo [ERROR] Wystapil problem podczas tworzenia zadania.
)

pause
