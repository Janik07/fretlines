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
# Старый сервер дописывает начатые ответы (банк звуков — 40 МБ) и держит порт: ждём, пока
# он освободится, — Codespaces пробрасывает только 8080.
for _ in $(seq 1 30); do
  (exec 3<>/dev/tcp/127.0.0.1/8080) 2>/dev/null || break
  sleep 1
done
bash .devcontainer/start.sh
for _ in $(seq 1 30); do
  curl -sf -o /dev/null http://127.0.0.1:8080/api/health && break
  sleep 1
done
echo "== Fretlines обновлён и перезапущен: $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/health)"
