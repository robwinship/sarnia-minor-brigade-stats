@echo off
REM Commit and push all changes in the repo

git add .
git commit -m "Update site content"
git push

echo Changes committed and pushed to remote repository.
pause
