"""Фоновый воркер Fretlines: разбирает загруженные песни (очередь RQ в Redis)."""

from importlib.metadata import version

__version__ = version("fretlines-worker")
