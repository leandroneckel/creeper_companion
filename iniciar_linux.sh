#!/usr/bin/env bash
# Abre o Creeper Companion (cria o ambiente na primeira vez).
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "Preparando o ambiente pela primeira vez..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi
nohup .venv/bin/python main.py >/dev/null 2>&1 &
