# Studyme3 Claude Code Notes

Studyme3 is a long-memory Discord bot written in Python.

## Project layout

- `bot.py` — Discord bot entrypoint. Run with `python bot.py <bot-key>` where bot keys are defined in local `bots.json`.
- `llm.py` — Gemini/Grok/OpenAI-compatible LLM client and function-calling loop.
- `memory.py` — ChromaDB-backed long-term memory.
- `relations.py` — SQLite relationship graph and nickname/user-id ledger.
- `tools.py` — callable tools used by the LLM.
- `config.py` — environment-variable based configuration.

## Local/private files

Do not commit or expose secrets or runtime data:

- `.env`
- `bots.json`
- `data/`
- `images/`
- `logs/`

Use `.env.example` and `bots.example.json` as templates. Remote/cloud sessions need their own environment variables for real bot runs.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## Useful checks

```bash
python -m py_compile bot.py config.py llm.py memory.py persona.py relations.py tools.py web.py
```

## Running bots

```bash
python bot.py ina
python bot.py nara
```

Only run real bots when valid Discord/Gemini secrets are configured in the session environment. Avoid starting duplicate bot processes with the same token.
