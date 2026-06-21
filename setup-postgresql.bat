@echo off
chcp 65001 >nul
cd /d "%~dp0"

if exist "C:\Program Files\PostgreSQL\18\bin\psql.exe" (
  set "PATH=C:\Program Files\PostgreSQL\18\bin;%PATH%"
)

sc query postgresql-x64-18 | find "RUNNING" >nul
if errorlevel 1 (
  echo Запуск postgresql-x64-18...
  net start postgresql-x64-18 2>nul
)

if not exist ".venv\Scripts\python.exe" (
  echo Сначала запустите setup.bat
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat
set POSTGRES_DB=newsystem
set POSTGRES_USER=newsystem
set POSTGRES_PASSWORD=newsystem

python scripts\setup_postgresql.py
if errorlevel 1 pause & exit /b 1

echo.
echo Миграции...
python manage.py migrate --noinput
echo.
echo Суперпользователь (по желанию): python manage.py createsuperuser
pause
