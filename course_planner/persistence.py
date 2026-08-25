"""SQLite persistence shared by LangGraph checkpoints and planner jobs."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATABASE = _PROJECT_ROOT / ".data" / "planner.sqlite3"


def database_path() -> Path:
    configured = os.getenv("PLANNER_DATABASE_PATH", "").strip()
    path = Path(configured).expanduser() if configured else _DEFAULT_DATABASE
    if not path.is_absolute():
        path = (_PROJECT_ROOT / path).resolve()
    return path


def _prepare_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.is_file():
        raise RuntimeError(f"PLANNER_DATABASE_PATH is not a file: {path}")


def connect_database() -> sqlite3.Connection:
    """Open one hardened, thread-capable SQLite connection."""
    path = database_path()
    _prepare_database(path)
    connection = sqlite3.connect(
        path,
        timeout=30,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA synchronous=NORMAL")
    if path.exists():
        path.chmod(0o600)
    return connection


@contextmanager
def planner_checkpointer() -> Iterator[SqliteSaver]:
    """Yield a strict-serialization SQLite checkpointer for one graph run."""
    connection = connect_database()
    try:
        serializer = JsonPlusSerializer(allowed_msgpack_modules=None)
        saver = SqliteSaver(connection, serde=serializer)
        saver.setup()
        yield saver
    finally:
        connection.close()


def database_ready() -> tuple[bool, str]:
    try:
        connection = connect_database()
        try:
            connection.execute("SELECT 1").fetchone()
        finally:
            connection.close()
        return True, str(database_path())
    except Exception as exc:  # noqa: BLE001 - readiness must return a diagnostic
        return False, str(exc)
