"""Pengelolaan sesi percakapan untuk antarmuka web."""

from __future__ import annotations
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

SESSION_TTL_SECONDS = 60 * 60
MAX_SESSIONS = 200


@dataclass
class Session:
    session_id: str
    pipeline: object
    created_at: float
    last_seen_at: float
    lock: threading.Lock = field(default_factory=threading.Lock)


class SessionStore:
    """Simpan satu pipeline per sesi, lengkap dengan pembersihan sesi lama."""

    def __init__(
        self,
        pipeline_factory: Callable[[], object],
        ttl_seconds: int = SESSION_TTL_SECONDS,
        max_sessions: int = MAX_SESSIONS,
    ):
        self._factory = pipeline_factory
        self._ttl = ttl_seconds
        self._max = max_sessions
        self._sessions: dict[str, Session] = {}
        self._guard = threading.Lock()

    def _purge_expired(self, now: float) -> None:
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.last_seen_at > self._ttl
        ]
        for sid in expired:
            del self._sessions[sid]

    def _enforce_capacity(self) -> None:
        excess = len(self._sessions) - self._max
        if excess <= 0:
            return
        by_age = sorted(self._sessions.items(), key=lambda kv: kv[1].last_seen_at)
        for sid, _ in by_age[:excess]:
            del self._sessions[sid]

    def get_or_create(self, session_id: str | None) -> Session:
        now = time.time()
        with self._guard:
            self._purge_expired(now)

            if session_id and session_id in self._sessions:
                session = self._sessions[session_id]
                session.last_seen_at = now
                return session

            new_id = secrets.token_urlsafe(16)
            session = Session(
                session_id=new_id,
                pipeline=self._factory(),
                created_at=now,
                last_seen_at=now,
            )
            self._sessions[new_id] = session
            self._enforce_capacity()
            return session

    def reset(self, session_id: str | None) -> Session:
        session = self.get_or_create(session_id)
        with session.lock:
            session.pipeline.reset()
        return session

    def count(self) -> int:
        with self._guard:
            return len(self._sessions)
