import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .privacy import ROOT

DB_PATH = ROOT / "data" / "reactionroles.db"


@dataclass(frozen=True, slots=True)
class Entry:
    id: int
    guild_id: int
    channel_id: int
    message_id: int
    emoji_key: str
    emoji_api: str
    role_id: int
    type: str


_COLUMNS = "id, guild_id, channel_id, message_id, emoji_key, emoji_api, role_id, type"


class Store:
    def __init__(self, path: Path = DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS reaction_roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    emoji_key TEXT NOT NULL,
                    emoji_api TEXT NOT NULL,
                    role_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    UNIQUE (message_id, emoji_key)
                )
                """
            )

    def close(self):
        with self._lock:
            self._db.close()

    def all(self) -> list[Entry]:
        with self._lock:
            rows = self._db.execute(f"SELECT {_COLUMNS} FROM reaction_roles").fetchall()
        return [Entry(*row) for row in rows]

    def add(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        emoji_key: str,
        emoji_api: str,
        role_id: int,
        type_: str,
        created_by: int,
    ) -> Entry | None:
        try:
            with self._lock, self._db:
                cur = self._db.execute(
                    "INSERT INTO reaction_roles (guild_id, channel_id, message_id, emoji_key, emoji_api,"
                    " role_id, type, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (guild_id, channel_id, message_id, emoji_key, emoji_api, role_id, type_, created_by, int(time.time())),
                )
        except sqlite3.IntegrityError:
            return None
        return Entry(cur.lastrowid, guild_id, channel_id, message_id, emoji_key, emoji_api, role_id, type_)

    def get(self, entry_id: int, guild_id: int) -> Entry | None:
        with self._lock:
            row = self._db.execute(
                f"SELECT {_COLUMNS} FROM reaction_roles WHERE id = ? AND guild_id = ?", (entry_id, guild_id)
            ).fetchone()
        return Entry(*row) if row else None

    def delete(self, ids: list[int]):
        if not ids:
            return
        with self._lock, self._db:
            self._db.executemany("DELETE FROM reaction_roles WHERE id = ?", [(i,) for i in ids])
