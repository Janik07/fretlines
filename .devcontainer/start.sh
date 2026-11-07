#!/usr/bin/env bash
# Каждый старт Codespace: поднимаем Fretlines на порту 8080. Журнал — /tmp/fretlines.log.
# setsid -f уводит процесс в свою сессию: иначе Codespaces гасит его вместе с этим скриптом.
cd "$(dirname "$0")/.."
if pgrep -f "python -m fretlines_api" >/dev/null 2>&1; then
  exit 0
fi
setsid -f .venv/bin/python -m fretlines_api --no-browser --host 0.0.0.0 --port 8080 \
  >/tmp/fretlines.log 2>&1 </dev/null
# Пустая библиотека — кладём демо-песню, чтобы было что открыть сразу.
setsid -f .venv/bin/python scripts/seed_demo.py >/tmp/fretlines-seed.log 2>&1 </dev/null
