@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Primero ejecuta INSTALAR.bat
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pytest -q
pause
