@echo off
setlocal EnableDelayedExpansion

REM ================================================================
REM  Sarnia Brigade -- Backup Utility
REM
REM  - Increments version.txt by 0.01
REM  - Prepends an entry to CHANGELOG.md
REM  - Zips the project folder to ..\Sarnia_Brigade_Backups\
REM    with filename:  SarniaBrigade_v<ver>_<yyyy-MM-dd_HH-mm-ss>.zip
REM ================================================================

REM Resolve the project directory (folder containing this script)
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

set "VERSION_FILE=%PROJECT_DIR%\version.txt"
set "CHANGELOG_FILE=%PROJECT_DIR%\CHANGELOG.md"

REM Backup folder sits alongside the project directory
for %%i in ("%PROJECT_DIR%") do set "PARENT_DIR=%%~dpi"
set "BACKUP_DIR=%PARENT_DIR%Sarnia_Brigade_Backups"

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

REM --- Create backup directory if needed -------------------------
if not exist "%BACKUP_DIR%" (
    mkdir "%BACKUP_DIR%"
    echo   Created backup directory.
)

REM --- Zip the project folder ------------------------------------
echo   Creating archive...
powershell -NoProfile -Command "Compress-Archive -Path '%PROJECT_DIR%' -DestinationPath '%BACKUP_PATH%' -Force"
if %errorlevel% neq 0 (
    echo.
    echo   ERROR: Archive creation failed. Backup was not saved.
    pause
    exit /b 1
)
echo   Archive created successfully.

REM --- Update version.txt ----------------------------------------
echo %NEW_VERSION%> "%VERSION_FILE%"

REM --- Prepend entry to CHANGELOG.md -----------------------------
powershell -NoProfile -Command "$f='%CHANGELOG_FILE%'; $v='%NEW_VERSION%'; $d='%TS_LOG%'; $c=Get-Content $f -Raw; $e=[char]10+'## v'+$v+' - '+$d+[char]10+'- Backup created'+[char]10; $h='# Changelog'; Set-Content $f ($h+$e+$c.Substring($h.Length)) -NoNewline"
echo   Changelog updated.

echo.
echo  ================================================
echo   Done!  %BACKUP_NAME%
echo  ================================================
echo.
pause
