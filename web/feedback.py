"""Perekaman umpan balik pengguna atas rencana yang dihasilkan."""

from __future__ import annotations
import json
import threading
from datetime import datetime
from pathlib import Path

VALID_RATINGS = ("berguna", "tidak_berguna")
MAX_REASON_LENGTH = 500


class FeedbackStore:
    """Simpan umpan balik sebagai JSON Lines agar mudah diolah ulang."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def record(
        self,
        session_id: str,
        rating: str,
        reason: str = "",
        profile: dict | None = None,
        sources: list[str] | None = None,
        plan_excerpt: str = "",
    ) -> dict:
        if rating not in VALID_RATINGS:
            raise ValueError(
                f"Rating tidak dikenal: {rating}. Pilihan: {list(VALID_RATINGS)}"
            )

        entry = {
            "waktu": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "rating": rating,
            "alasan": (reason or "").strip()[:MAX_REASON_LENGTH],
            "profil": profile or {},
            "sumber": sources or [],
            "cuplikan_rencana": plan_excerpt[:300],
        }

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return entry

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        entries = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def summary(self) -> dict:
        entries = self.read_all()
        berguna = sum(1 for e in entries if e["rating"] == "berguna")
        total = len(entries)
        return {
            "total": total,
            "berguna": berguna,
            "tidak_berguna": total - berguna,
            "proporsi_berguna": round(berguna / total, 4) if total else None,
        }
