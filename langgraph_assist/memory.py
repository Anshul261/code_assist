from __future__ import annotations

import sqlite3
from pathlib import Path


class MemoryStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists memories (
                    id integer primary key autoincrement,
                    namespace text not null,
                    content text not null,
                    created_at datetime default current_timestamp
                )
                """
            )
            conn.execute(
                "create index if not exists idx_memories_namespace on memories(namespace)"
            )

    def remember(self, namespace: str, content: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "insert into memories(namespace, content) values (?, ?)",
                (namespace, content),
            )
            return int(cursor.lastrowid)

    def search(self, namespace: str, query: str = "", limit: int = 10) -> list[dict[str, str | int]]:
        like = f"%{query}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                select id, namespace, content, created_at
                from memories
                where namespace = ? and (? = '' or content like ?)
                order by id desc
                limit ?
                """,
                (namespace, query, like, limit),
            ).fetchall()
        return [
            {"id": row[0], "namespace": row[1], "content": row[2], "created_at": row[3]}
            for row in rows
        ]

