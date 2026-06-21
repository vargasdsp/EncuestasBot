"""
Persistence layer using SQLite.
Stores the last notified id_unico per source and a notification history.
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class Storage:
    def __init__(self, db_path: str = "/data/state.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS last_seen (
                    fuente      TEXT PRIMARY KEY,
                    id_unico    TEXT NOT NULL,
                    titulo      TEXT,
                    link        TEXT,
                    notified_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    fuente      TEXT NOT NULL,
                    id_unico    TEXT NOT NULL,
                    titulo      TEXT,
                    link        TEXT,
                    notified_at TEXT NOT NULL
                )
            """)
            # Track consecutive failures per source for alerting
            conn.execute("""
                CREATE TABLE IF NOT EXISTS failures (
                    fuente          TEXT PRIMARY KEY,
                    consecutive     INTEGER NOT NULL DEFAULT 0,
                    last_failure_at TEXT
                )
            """)
            conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_new(self, fuente: str, id_unico: str) -> bool:
        """Return True if this id_unico has not been notified before for this source."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id_unico FROM last_seen WHERE fuente = ?", (fuente,)
            ).fetchone()
        if row is None:
            return True
        return row["id_unico"] != id_unico

    def mark_notified(self, fuente: str, id_unico: str, titulo: str = "", link: str = "") -> None:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO last_seen (fuente, id_unico, titulo, link, notified_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(fuente) DO UPDATE SET
                    id_unico=excluded.id_unico,
                    titulo=excluded.titulo,
                    link=excluded.link,
                    notified_at=excluded.notified_at
                """,
                (fuente, id_unico, titulo, link, now),
            )
            conn.execute(
                "INSERT INTO history (fuente, id_unico, titulo, link, notified_at) VALUES (?,?,?,?,?)",
                (fuente, id_unico, titulo, link, now),
            )
            conn.commit()
        # Reset failure counter on success
        self.reset_failures(fuente)

    def get_last_seen(self, fuente: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM last_seen WHERE fuente = ?", (fuente,)
            ).fetchone()
        return dict(row) if row else None

    def get_all_last_seen(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM last_seen ORDER BY fuente").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Failure tracking
    # ------------------------------------------------------------------

    def record_failure(self, fuente: str) -> int:
        """Increment failure counter and return the new count."""
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO failures (fuente, consecutive, last_failure_at)
                VALUES (?, 1, ?)
                ON CONFLICT(fuente) DO UPDATE SET
                    consecutive = consecutive + 1,
                    last_failure_at = excluded.last_failure_at
                """,
                (fuente, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT consecutive FROM failures WHERE fuente = ?", (fuente,)
            ).fetchone()
        return row["consecutive"] if row else 1

    def reset_failures(self, fuente: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO failures (fuente, consecutive) VALUES (?, 0) "
                "ON CONFLICT(fuente) DO UPDATE SET consecutive = 0",
                (fuente,),
            )
            conn.commit()
