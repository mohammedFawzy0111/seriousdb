"""Module-level Python API for seriousdb"""

from threading import lock

from .cache import Cache
from .config import DB_FILE

_cache = Cache()
_load_lock = lock()

def _ensure_loaded() -> Cache:
    """Return the Module-level cache, loading it form disk on first use."""
    if _cache.db is None:
        with _load_lock:
            _cache.load(DB_FILE)
    return _cache

def get(key: str) -> str:
    """Return the value stored under `key`.

    Raises 

    ResourceNotFoundError
        if `key` does not exist
    ServiceUnavailableError
        if the database could not be loaded.
    """
    return _ensure_loaded().select(key)

def set(key: str, value: str) -> str:
    """Store `value` under `key` adn persist the change.

    Returns

    str  the stored value"""
    cache = _ensure_loaded()
    stored_value, _ = cache.insert(key, value)
    cache.flush()
    return stored_value

def delete(key: str) -> str:
    """Remove `key` and persist the change

    Raises

    ResourceNotFoundError
        if `key` does not exist.
    ServiceUnavailableError
        if the database could not be loaded.
    """
    cache = _ensure_loaded()
    value = cache.delete(key)
    cache.flush()
    return value
