#!/usr/bin/env bash
# Первое создание Codespace: Python-библиотеки, интерфейс и модели. Дальше — start.sh на каждом старте.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/0.13.7/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
export UV_PYTHON=python3.11 UV_PYTHON_DOWNLOADS=never

echo "== Python-библиотеки"
uv sync --frozen

echo "== Интерфейс"
(cd frontend && npm ci --no-fund --no-audit && npm run build)

echo "== Модели (Demucs, Beat This!, Basic Pitch, Whisper, банк звуков)"
uv run --no-sync python scripts/fetch_models.py

echo "== Fretlines готов"
