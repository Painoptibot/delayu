@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === newsystem: чистая установка ===
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Создание виртуального окружения Python...
  python -m venv .venv
  if errorlevel 1 (
    echo Не найден python. Установите Python 3.12+ или добавьте в PATH.
    pause
    exit /b 1
  )
) else (
  echo [1/4] .venv уже есть
)

echo [2/4] Установка зависимостей...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo PyPI недоступен — зеркало Aliyun...
  pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com
)
if errorlevel 1 (
  pause
  exit /b 1
)

if not exist ".env" (
  echo [3/4] Копирование .env.example -^> .env
  copy /Y .env.example .env >nul
) else (
  echo [3/4] .env уже есть
)

echo [4/4] Миграции Django...
python manage.py migrate --noinput
if errorlevel 1 (
  echo.
  echo Миграции не прошли. Сначала настройте PostgreSQL:
  echo   setup-postgresql.bat
  echo.
  pause
  exit /b 1
)

echo.
echo === Готово ===
echo Запуск: runserver.bat
echo API:    http://127.0.0.1:8000/api/health/
echo Админ:  http://127.0.0.1:8000/admin/
pause
