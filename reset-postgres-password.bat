@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
echo.
echo Reset postgres superuser password (temporary trust in pg_hba.conf)
echo Data: C:\laragon\www\postgres
echo.
.venv\Scripts\python.exe scripts\reset_postgres_password.py %*
set ERR=%ERRORLEVEL%
echo.
if not %ERR%==0 echo FAILED
pause
exit /b %ERR%
