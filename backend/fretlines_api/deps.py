"""Зависимости FastAPI: ресурсы, созданные при старте приложения (см. main.lifespan)."""

from fastapi import Request
from sqlalchemy import Engine

from fretlines_api.jobs import JobRunner
from fretlines_api.settings import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


def get_runner(request: Request) -> JobRunner:
    runner: JobRunner = request.app.state.runner
    return runner
