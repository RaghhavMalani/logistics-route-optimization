"""Unresolved write failures reported by the running refresh workers."""
from errno import EACCES, EDQUOT, EIO, ENOSPC, EROFS
from sqlite3 import DatabaseError
from threading import Lock

from sqlalchemy.exc import DBAPIError

_lock = Lock()
_failed_writers: set[str] = set()


def is_storage_error(error: Exception) -> bool:
    return (isinstance(error, (DatabaseError, DBAPIError)) or
            isinstance(error, OSError) and error.errno in (EACCES, EDQUOT, EIO, ENOSPC, EROFS))


def record_write(writer: str, *, ok: bool) -> None:
    with _lock:
        if ok:
            _failed_writers.discard(writer)
        else:
            _failed_writers.add(writer)


def failed_writes() -> list[str]:
    with _lock:
        return sorted(_failed_writers)
