"""База разборов: SQLite по умолчанию, через SQLAlchemy — чтобы потом перейти на PostgreSQL."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import Engine, Float, String, Text, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    artist: Mapped[str | None] = mapped_column(String(300), default=None)
    source_kind: Mapped[str] = mapped_column(String(8))  # file | url
    source_url: Mapped[str | None] = mapped_column(Text, default=None)
    filename: Mapped[str | None] = mapped_column(String(300), default=None)

    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued running done failed
    stage: Mapped[str | None] = mapped_column(String(16), default=None)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error_code: Mapped[str | None] = mapped_column(String(32), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    duration: Mapped[float | None] = mapped_column(Float, default=None)
    tempo: Mapped[float | None] = mapped_column(Float, default=None)
    key: Mapped[str | None] = mapped_column(String(8), default=None)
    device: Mapped[str | None] = mapped_column(String(8), default=None)
    # Состав группы, транспонирование и прочие настройки студии (JSON).
    setup: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)


def create_db_engine(url: str) -> Engine:
    sqlite = url.startswith("sqlite")
    engine = create_engine(
        url, connect_args={"check_same_thread": False, "timeout": 30} if sqlite else {}
    )
    if sqlite:

        @event.listens_for(engine, "connect")
        def _pragmas(connection: DBAPIConnection, _: object) -> None:
            # WAL: API читает, пока процесс анализа пишет прогресс.
            cursor = connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return engine


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        yield session
