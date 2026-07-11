#!/usr/bin/env bash
# Fiyox — create a virtual environment and install dependencies.
set -e

PYTHON="${PYTHON:-python3}"

echo "Creating virtual environment in .venv ..."
"$PYTHON" -m venv .venv

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Upgrading pip and installing dependencies ..."
python -m pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo ""
echo "Done. Next:"
echo "  source .venv/bin/activate    # activate the environment"
echo "  python seed.py               # load demo data"
echo "  uvicorn app.main:app --reload"
