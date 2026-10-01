@echo off
rem Abre o Creeper Companion (cria o ambiente na primeira vez).
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Preparando o ambiente pela primeira vez...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
start "" ".venv\Scripts\pythonw.exe" main.py
