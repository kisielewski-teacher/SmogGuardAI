@echo off
chcp 65001 >nul
setlocal
echo === Aktualizacja przegladarki Microsoft Edge ===
call :wersja WER_PRZED
echo [INFO] Wersja Edge przed aktualizacja: %WER_PRZED%
echo [INFO] Zamknij wszystkie okna Edge (zapisz prace w przegladarce).
pause
taskkill /f /im msedge.exe >nul 2>&1

REM Sposob 1: winget (Windows 10/11 z Instalatorem aplikacji)
where winget >nul 2>&1
if not errorlevel 1 (
    echo [INFO] Sposob 1: winget...
    winget upgrade --id Microsoft.Edge --silent --accept-source-agreements --accept-package-agreements
    call :wersja WER_PO
    if not "%WER_PO%"=="%WER_PRZED%" goto :gotowe
)

REM Sposob 2: wbudowany aktualizator Edge
set "EU=%ProgramFiles(x86)%\Microsoft\EdgeUpdate\MicrosoftEdgeUpdate.exe"
if exist "%EU%" (
    echo [INFO] Sposob 2: aktualizator Edge, to moze potrwac kilka minut...
    "%EU%" /ua /installsource scheduler
    timeout /t 90 /nobreak >nul
    call :wersja WER_PO
    if not "%WER_PO%"=="%WER_PRZED%" goto :gotowe
)

REM Sposob 3: oficjalny instalator ze strony Microsoft
echo [INFO] Sposob 3: pobieranie oficjalnego instalatora Edge...
set "INST=%TEMP%\MicrosoftEdgeSetup.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest 'https://go.microsoft.com/fwlink/?linkid=2109047' -OutFile '%INST%'; if ((Get-Item '%INST%').Length -lt 500000) { exit 1 }"
if errorlevel 1 ( echo [ERR] Automatyczne pobranie nie powiodlo sie. Otwieram strone Microsoft, pobierz Edge recznie. & start "" "https://www.microsoft.com/edge/download" & pause & exit /b 1 )
echo [INFO] Uruchamiam instalator (potwierdz okno kontroli konta, jesli sie pojawi)...
"%INST%"
timeout /t 60 /nobreak >nul
call :wersja WER_PO

:gotowe
echo.
echo [INFO] Wersja Edge po aktualizacji: %WER_PO%
if "%WER_PO%"=="%WER_PRZED%" (
    echo [UWAGA] Wersja sie nie zmienila. Jesli Edge jest aktualny, nic wiecej nie trzeba.
    echo         Jesli nie, otworz edge://settings/help albo uruchom ten plik jako administrator.
) else (
    echo [OK] Edge zaktualizowany. Uruchom ponownie SmogGuardAI.
)
pause
exit /b 0

:wersja
set "%~1=nieznana"
for /f "tokens=3" %%v in ('reg query "HKCU\Software\Microsoft\Edge\BLBeacon" /v version 2^>nul ^| "%SystemRoot%\System32\find.exe" "version"') do set "%~1=%%v"
exit /b 0
