from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from fretlines_api import __version__
from fretlines_api.db import create_db_engine, init_db
from fretlines_api.jobs import JobRunner
from fretlines_api.routes import health, meta, songs
from fretlines_api.settings import Settings, load_settings

_NOT_BUILT = """<!doctype html><html lang="ru"><meta charset="utf-8"><title>Fretlines</title>
<body style="background:#0a0a0b;color:#ecebe7;font:16px system-ui;padding:48px">
<h1 style="font-weight:600">Интерфейс ещё не собран</h1>
<p>Запусти <code>start.bat</code> — он соберёт его сам. Или вручную:
<code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>.</p></body></html>"""


class SpaFiles(StaticFiles):
    """Статика собранного фронтенда; неизвестные пути отдают index.html (маршруты React)."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404:
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404:
            return await super().get_response("index.html", scope)
        return response


def create_app(settings: Settings | None = None, *, run_jobs: bool = True) -> FastAPI:
    app_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app_settings.storage_dir.mkdir(parents=True, exist_ok=True)
        engine = create_db_engine(app_settings.sqlalchemy_url)
        init_db(engine)
        runner = JobRunner(
            engine,
            app_settings.storage_dir.resolve(),
            app_settings.sqlalchemy_url,
            app_settings.device,
        )
        if run_jobs:
            runner.start()
        app.state.settings = app_settings
        app.state.engine = engine
        app.state.runner = runner
        try:
            yield
        finally:
            if run_jobs:
                runner.stop()
            engine.dispose()

    app = FastAPI(
        title="Fretlines API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    for module in (health, meta, songs):
        app.include_router(module.router, prefix="/api")

    dist = Path(app_settings.frontend_dir)
    if (dist / "index.html").exists():
        app.mount("/", SpaFiles(directory=dist, html=True), name="frontend")
    else:

        @app.get("/", include_in_schema=False)
        def not_built() -> HTMLResponse:
            return HTMLResponse(_NOT_BUILT)

    return app


app = create_app()
