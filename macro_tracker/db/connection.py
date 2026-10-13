"""Conexión SQLite y migraciones versionadas."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from macro_tracker.config import db_path

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
LATEST_VERSION = 1


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Abre (y migra) la base. `path=":memory:"` sirve para pruebas."""
    target = str(path) if path is not None else str(db_path())
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: Streamlit atiende cada sesión en un hilo distinto.
    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if target != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    has_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if not has_table:
        return 0
    row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    return int(row["v"] or 0)


def migrate(conn: sqlite3.Connection) -> None:
    """Lleva la base a la última versión. Hoy solo existe la v1; las futuras se
    añaden como `schema_vN.sql` y se aplican en orden."""
    current = schema_version(conn)
    if current > LATEST_VERSION:
        raise RuntimeError(
            f"La base de datos es de una versión más nueva ({current}) que la app ({LATEST_VERSION})."
        )
    if current == 0:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        conn.commit()
