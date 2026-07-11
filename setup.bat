@echo off
REM Fiyox - create a virtual environment and install dependencies.

echo Creating virtual environment in .venv ...
python -m venv .venv

call .venv\Scripts\activate.bat

echo Upgrading pip and installing dependencies ...
python -m pip install --upgrade pip
pip install -r requirements.txt

if not exist .env (
    copy .env.example .env
    echo Created .env from .env.example
)

echo.
echo Done. Next:
echo   .venv\Scripts\activate.bat    ^&^& activate the environment
echo   python seed.py                ^&^& load demo data
echo   uvicorn app.main:app --reload
