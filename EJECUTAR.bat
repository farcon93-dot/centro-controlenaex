@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Primero ejecuta INSTALAR.bat
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
streamlit run app.py
pause
