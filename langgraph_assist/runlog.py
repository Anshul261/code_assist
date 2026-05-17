from __future__ import annotations

import contextvars
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any


_active_session: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "active_log_session", default=None
)
_logs: dict[str, list[dict[str, Any]]] = defaultdict(list)
_lock = threading.Lock()


@contextmanager
def run_context(session_id: str):
    token = _active_session.set(session_id)
    try:
        yield
    finally:
        _active_session.reset(token)


def start_run(session_id: str, message: str) -> None:
    with _lock:
        _logs[session_id] = []
    append_log("run", "Run started", _truncate(message, 220), session_id=session_id)


def append_log(
    kind: str,
    title: str,
    detail: str = "",
    *,
    session_id: str | None = None,
) -> None:
    target = session_id or _active_session.get()
    if not target:
        return
    event = {
        "time": time.strftime("%H:%M:%S"),
        "kind": kind,
        "title": title,
        "detail": _truncate(detail, 1000),
    }
    with _lock:
        _logs[target].append(event)


def get_logs(session_id: str) -> list[dict[str, Any]]:
    with _lock:
        return list(_logs.get(session_id, []))


def _truncate(value: str, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."

