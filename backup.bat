@echo off
setlocal EnableExtensions DisableDelayedExpansion

REM ================================================================
REM  Sarnia Brigade -- Backup Utility
REM
REM  - Increments version.txt by 0.01
REM  - Prepends an entry to CHANGELOG.md
REM  - Zips the project folder to .\backups\
REM    with filename:  SarniaBrigade_v<ver>_<yyyy-MM-dd_HH-mm-ss>.zip
REM  - Keeps only the 10 most recent backups
REM ================================================================

REM Resolve the project directory (folder containing this script)
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

set "VERSION_FILE=%PROJECT_DIR%\version.txt"
set "CHANGELOG_FILE=%PROJECT_DIR%\CHANGELOG.md"

REM Backup folder is inside the project directory
set "BACKUP_DIR=C:\Users\Admin\OneDrive\Documents\Coding\Sarnia_Brigade_Backups"

echo.
echo  ================================================
echo   Sarnia Brigade Backup Utility
echo  ================================================

REM --- Read current version and increment by 0.01 ---------------
for /f "usebackq tokens=*" %%v in ("%VERSION_FILE%") do set "CURRENT_VERSION=%%v"
for /f %%v in ('powershell -NoProfile -Command "[decimal]$v=[decimal]'%CURRENT_VERSION%'+[decimal]'0.01';$v.ToString('0.00')"') do set "NEW_VERSION=%%v"

REM --- Build timestamps ------------------------------------------
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'"') do set "TS_FILE=%%d"
for /f "tokens=*" %%d in ('powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set "TS_LOG=%%d"

REM --- Assemble backup path --------------------------------------
set "BACKUP_NAME=SarniaBrigade_v%NEW_VERSION%_%TS_FILE%.zip"
set "BACKUP_PATH=%BACKUP_DIR%\%BACKUP_NAME%"

echo   Version  : %CURRENT_VERSION% -^> %NEW_VERSION%
echo   File     : %BACKUP_NAME%
echo   Location : %BACKUP_DIR%
echo.

REM --- Prompt for backup note (optional) ------------------------
set "BACKUP_NOTE="
set /p "BACKUP_NOTE=  Enter backup note (optional): "
if not defined BACKUP_NOTE set "BACKUP_NOTE=Backup created"

REM --- Create backup directory if needed -------------------------
if not exist "%BACKUP_DIR%" (
    mkdir "%BACKUP_DIR%"
    echo   Created backup directory.
)

REM --- Zip the project folder (excluding large/unnecessary folders) ---
echo   Creating archive...
powershell -NoProfile -Command "$exclude = '.venv|.venv-1|.git|.github|.vscode'; Get-ChildItem -Path '%PROJECT_DIR%' -Recurse -Force | Where-Object {$_.FullName -notmatch $exclude} | Select-Object -ExpandProperty FullName | Compress-Archive -DestinationPath '%BACKUP_PATH%' -Force"
if %errorlevel% neq 0 (
    echo.
    echo   ERROR: Archive creation failed. Backup was not saved.
    pause
    exit /b 1
)
echo   Archive created successfully.

REM --- Clean up old backups (keep only 10 most recent) -----------
echo   Cleaning up old backups (keeping 10 most recent)...
powershell -NoProfile -Command "Get-ChildItem -Path '%BACKUP_DIR%' -Filter '*.zip' -File | Sort-Object -Property LastWriteTime -Descending | Select-Object -Skip 10 | ForEach-Object { Remove-Item $_.FullName -Force; Write-Host '   Deleted: ' $_.Name }"

REM --- Update version.txt ----------------------------------------
echo %NEW_VERSION%> "%VERSION_FILE%"

REM --- Prepend entry to CHANGELOG.md -----------------------------
powershell -NoProfile -Command "$f='%CHANGELOG_FILE%'; $v='%NEW_VERSION%'; $d='%TS_LOG%'; $n=$env:BACKUP_NOTE; if ([string]::IsNullOrWhiteSpace($n)) { $n='Backup created' }; $c=Get-Content $f -Raw; $e=[char]10+'## v'+$v+' - '+$d+[char]10+'- '+$n+[char]10; $h='# Changelog'; Set-Content $f ($h+$e+$c.Substring($h.Length)) -NoNewline"
echo   Changelog updated.

echo.
echo  ================================================
echo   Done!  %BACKUP_NAME%
echo  ================================================
echo.
pause
