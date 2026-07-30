@echo off
cd /d "%~dp0"
echo Creando entorno virtual...
py -3.12 -m venv .venv
if errorlevel 1 py -3.11 -m venv .venv
if errorlevel 1 python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .streamlit\secrets.toml copy .streamlit\secrets.toml.example .streamlit\secrets.toml
echo.
echo Instalacion terminada.
echo Ahora abre .streamlit\secrets.toml y pega tus claves.
pause
