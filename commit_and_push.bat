@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Commit and push with basic safety checks.
REM Uses gc.auto=0 for push to reduce OneDrive lock conflicts in .git/objects.

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

where git >nul 2>&1
if errorlevel 1 (
	echo ERROR: git is not available in PATH.
	exit /b 1
)

REM Disable automatic maintenance for this repo to avoid interactive
REM '.git/objects/*' deletion prompts on Windows/OneDrive paths.
git config --local gc.auto 0 >nul 2>&1
git config --local maintenance.auto false >nul 2>&1

for /f "usebackq delims=" %%B in (`git rev-parse --abbrev-ref HEAD`) do set "BRANCH=%%B"
if not defined BRANCH set "BRANCH=main"

git -c gc.auto=0 -c maintenance.auto=false add -A
if errorlevel 1 (
	echo ERROR: failed to stage changes.
	exit /b 1
)

git -c gc.auto=0 -c maintenance.auto=false diff --cached --quiet
if not errorlevel 1 (
	echo No changes to commit.
	exit /b 0
)

for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'"`) do set "STAMP=%%T"
git -c gc.auto=0 -c maintenance.auto=false commit -m "chore: content update %STAMP%"
if errorlevel 1 (
	echo ERROR: commit failed.
	exit /b 1
)

echo Syncing with origin/%BRANCH% before push...
git -c gc.auto=0 -c maintenance.auto=false pull --rebase --autostash origin "%BRANCH%"
if errorlevel 1 (
	echo ERROR: pull --rebase failed. Attempting to abort any in-progress rebase.
	git -c gc.auto=0 -c maintenance.auto=false rebase --abort >nul 2>&1
	echo Commit remains local-only. Resolve git conflicts/state, then push manually.
	exit /b 1
)

git -c gc.auto=0 -c maintenance.auto=false push origin "%BRANCH%"
if errorlevel 1 (
	echo Push failed. Your commit is local and safe.
	echo Close OneDrive-heavy file activity and retry this script.
	exit /b 1
)

echo Changes committed and pushed to origin/%BRANCH%.
exit /b 0
