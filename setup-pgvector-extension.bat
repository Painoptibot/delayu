@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
echo.
echo Step 2: CREATE EXTENSION vector (postgres superuser)
echo.
.venv\Scripts\python.exe scripts\enable_pgvector_extension.py %*
set ERR=%ERRORLEVEL%
echo.
if %ERR%==0 (
  echo [OK] Check:
  .venv\Scripts\python.exe scripts\check_pgvector.py
) else (
  echo [FAIL] see setup-pgvector.log
  type setup-pgvector.log 2>nul
)
echo.
pause
exit /b %ERR%
