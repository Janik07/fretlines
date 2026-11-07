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

echo "== Модели (Demucs, Beat This!)"
export HF_HOME="$PWD/.models/hf" TORCH_HOME="$PWD/.models/torch" HF_HUB_DISABLE_TELEMETRY=1
uv run --no-sync python -c "from demucs.pretrained import get_model; get_model('htdemucs_6s')"
uv run --no-sync python -c "from beat_this.inference import load_checkpoint; load_checkpoint('final0')"

echo "== Fretlines готов"
