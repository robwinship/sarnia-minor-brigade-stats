@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Sarnia Brigade local updater
REM - Runs scraper\scrape.py using local .venv Python
REM - Commits all tracked repo changes after scrape
REM - Pushes to current branch

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo ERROR: Python not found at "%PYTHON_EXE%"
    echo Ensure your virtual environment exists at .venv\Scripts\python.exe
    exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: git is not available in PATH.
    exit /b 1
)

for /f "usebackq delims=" %%B in (`git rev-parse --abbrev-ref HEAD`) do set "BRANCH=%%B"
if not defined BRANCH set "BRANCH=main"

echo Syncing with origin/%BRANCH% before running scraper...
git pull --rebase --autostash origin "%BRANCH%"
if errorlevel 1 (
    echo ERROR: pre-run pull --rebase failed. Attempting to abort any in-progress rebase.
    git rebase --abort >nul 2>&1
    echo Resolve git conflicts/state first, then re-run this script.
    exit /b 1
)

echo ------------------------------------------------------------
echo Running local update at %DATE% %TIME%
echo Repo: %ROOT%
echo ------------------------------------------------------------

call "%ROOT%\cp_credentials.bat"

"%PYTHON_EXE%" "%ROOT%\scraper\scrape.py"
if errorlevel 1 (
    echo ERROR: scraper failed.
    exit /b 1
)

git add -u
if errorlevel 1 (
    echo ERROR: failed to stage tracked changes
    exit /b 1
)

git diff --cached --quiet
if not errorlevel 1 (
    echo No tracked changes detected. Nothing to commit.
    exit /b 0
)

for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'"`) do set "STAMP=%%T"

git commit -m "chore: local scheduled season update %STAMP%"
if errorlevel 1 (
    echo ERROR: commit failed.
    exit /b 1
)

echo Syncing with origin/%BRANCH% before push...
git pull --rebase --autostash origin "%BRANCH%"
if errorlevel 1 (
    echo ERROR: pull --rebase failed. Attempting to abort any in-progress rebase.
    git rebase --abort >nul 2>&1
    echo Commit remains local-only. Resolve git conflicts/state, then push manually.
    exit /b 1
)

git push origin "%BRANCH%"
if errorlevel 1 (
    echo Push rejected; fetching latest and retrying once...
    git fetch origin "%BRANCH%"
    if errorlevel 1 (
        echo ERROR: fetch failed. Commit remains local-only.
        exit /b 1
    )
    git rebase "origin/%BRANCH%"
    if errorlevel 1 (
        echo ERROR: rebase failed during retry. Attempting rebase abort.
        git rebase --abort >nul 2>&1
        echo Commit remains local-only. Resolve manually.
        exit /b 1
    )
    git push origin "%BRANCH%"
    if errorlevel 1 (
        echo ERROR: push failed after retry. Commit remains local-only.
        exit /b 1
    )
)

echo Update complete and pushed to %BRANCH%.
exit /b 0
