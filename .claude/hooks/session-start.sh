#!/usr/bin/env bash
set -euo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(pwd)}"

if [ ! -d .venv ]; then
  python -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt >/dev/null

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "Created local .env from .env.example. Fill remote/session secrets before running real Discord bots."
fi

python -m py_compile bot.py config.py llm.py memory.py persona.py relations.py tools.py web.py
