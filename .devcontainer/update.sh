#!/usr/bin/env bash
# Обновить запущенный Codespace до свежей версии: код, библиотеки, интерфейс, модели — и перезапуск.
# Запуск в терминале Codespace: bash .devcontainer/update.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
export UV_PYTHON=python3.11 UV_PYTHON_DOWNLOADS=never

echo "== Код"
git pull --ff-only

echo "== Python-библиотеки"
uv sync --frozen

echo "== Интерфейс"
(cd frontend && npm ci --no-fund --no-audit && npm run build)

echo "== Модели"
uv run --no-sync python scripts/fetch_models.py

echo "== Перезапуск"
pkill -f "python -m fretlines_api" || true
sleep 2
bash .devcontainer/start.sh
echo "== Fretlines обновлён и перезапущен"
