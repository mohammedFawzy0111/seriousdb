"""SeriousDB, a small key-value store served over HTTP with FastAPI."""

from .api import get, set, delete
__all__ = ["get", "set", "delete"]
