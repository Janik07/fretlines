# syntax=docker/dockerfile:1
# Сборка для Hugging Face Space (см. deploy/huggingface). Дома Docker не нужен — там start.bat.

FROM node:24-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    HOME=/app \
    XDG_CACHE_HOME=/app/.cache \
    NUMBA_CACHE_DIR=/app/.cache/numba \
    HF_HOME=/app/.models/hf \
    TORCH_HOME=/app/.models/torch \
    HF_HUB_DISABLE_TELEMETRY=1 \
    FRETLINES_HOST=0.0.0.0 \
    FRETLINES_PORT=7860

WORKDIR /app

# Сначала только манифесты: слой с библиотеками пересобирается, лишь когда меняется uv.lock.
COPY pyproject.toml uv.lock ./
COPY arranger/pyproject.toml arranger/
COPY backend/pyproject.toml backend/
COPY worker/pyproject.toml worker/
RUN uv sync --frozen --no-dev --no-install-workspace

COPY arranger/ arranger/
COPY backend/ backend/
COPY worker/ worker/
RUN uv sync --frozen --no-dev

# Модели качаем при сборке, чтобы первый разбор не ждал загрузки.
RUN python -c "from demucs.pretrained import get_model; get_model('htdemucs_6s')" \
 && python -c "from beat_this.inference import load_checkpoint; load_checkpoint('final0')"

COPY --from=web /web/dist frontend/dist

# Hugging Face запускает контейнер от пользователя 1000 — ему нужны права на данные и кэши.
RUN mkdir -p storage .cache/numba && chown -R 1000:1000 /app

USER 1000
EXPOSE 7860
CMD ["python", "-m", "fretlines_api", "--no-browser"]
