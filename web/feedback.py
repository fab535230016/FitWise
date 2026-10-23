"""Perekaman umpan balik pengguna atas rencana yang dihasilkan."""

from __future__ import annotations
import json
import threading
from datetime import datetime
from pathlib import Path

VALID_RATINGS = ("berguna", "tidak_berguna")
MAX_REASON_LENGTH = 500
PUBLIC_PROFILE_FIELDS = ("Tujuan latihan", "Level pengalaman")
MAX_PUBLIC_CONTEXT_LENGTH = 60


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
        tampilkan: bool = False,
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
            "tampilkan": bool(tampilkan),
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

    def public_reviews(self, limit: int = 6, offset: int = 0) -> dict:
        """Ulasan yang boleh tampil di antarmuka, terbaru lebih dahulu.

        Hanya masukan yang pemiliknya mencentang persetujuan dan mengisi alasan
        yang ikut. Pengenal sesi, riwayat cedera, usia, sumber, dan cuplikan
        rencana tidak pernah dikirim ke luar.
        """
        shown = [
            e for e in self.read_all()
            if e.get("tampilkan") is True and e.get("alasan")
        ]
        shown.reverse()
        return {
            "jumlah_ulasan": len(shown),
            "ulasan": [self._public_view(e) for e in shown[offset:offset + limit]],
        }

    @staticmethod
    def _public_view(entry: dict) -> dict:
        profil = entry.get("profil") or {}
        konteks = {}
        for label in PUBLIC_PROFILE_FIELDS:
            nilai = str(profil.get(label) or "").strip()
            if nilai and not nilai.startswith("("):
                konteks[label] = nilai[:MAX_PUBLIC_CONTEXT_LENGTH]
        return {
            "tanggal": entry["waktu"][:10],
            "rating": entry["rating"],
            "alasan": entry["alasan"],
            "konteks": konteks,
        }
