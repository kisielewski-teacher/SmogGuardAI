@echo off
chcp 65001 >nul
setlocal
set "REPO=kisielewski-teacher/SmogGuardAI"
set "DEST=%USERPROFILE%\SmogGuardAI"
set "TMPD=%TEMP%\smogguard_dl"
echo === Instalacja SmogGuardAI ===
if exist "%TMPD%" rmdir /s /q "%TMPD%"
mkdir "%TMPD%"
echo [INFO] Pobieranie projektu z GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest 'https://github.com/%REPO%/archive/refs/heads/main.zip' -OutFile '%TMPD%\p.zip'; Expand-Archive '%TMPD%\p.zip' '%TMPD%' -Force"
if errorlevel 1 ( echo [ERR] Pobieranie nie powiodlo sie. Sprawdz internet. & pause & exit /b 1 )
if not exist "%TMPD%\SmogGuardAI-main\START.bat" ( echo [ERR] Pobrane pliki sa niekompletne. & pause & exit /b 1 )
echo [INFO] Kopiowanie do %DEST% ...
robocopy "%TMPD%\SmogGuardAI-main" "%DEST%" /E /NFL /NDL /NJH /NJS >nul
if errorlevel 8 ( echo [ERR] Kopiowanie nie powiodlo sie. & pause & exit /b 1 )
rmdir /s /q "%TMPD%"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\SmogGuardAI.lnk');$s.TargetPath='%DEST%\START.bat';$s.WorkingDirectory='%DEST%';$s.Save()"
echo [OK] Zainstalowano. Skrot SmogGuardAI jest na pulpicie. Uruchamiam...
call "%DEST%\START.bat"
