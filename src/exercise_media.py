"""Pemeta ilustrasi gerakan.

Komponen ini berjalan SETELAH plan generator dan compliance checker, dan tidak
pernah mengubah teks rencana. Tugasnya hanya satu: menemukan nama gerakan yang
disebut pada rencana, lalu melampirkan ilustrasi dan tata cara pelaksanaannya
dari katalog `data/gerakan/katalog_gerakan.json`.

Dua sifat berikut disengaja dan penting untuk metodologi:

1. Pencocokan bersifat deterministik (pencocokan alias berbasis ekspresi
   reguler), bukan hasil model bahasa. Karena itu tidak ada panggilan API
   tambahan, hasilnya dapat diulang persis, dan tidak ada risiko halusinasi
   nama gerakan.
2. Teks langkah pelaksanaan berasal dari katalog yang disusun manual, bukan
   dari keluaran model. Dengan begitu skor faithfulness dan groundedness
   terhadap literatur tetap dihitung atas teks rencana yang sama seperti
   sebelum fitur ini ada.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from src.citations import strip_source_markers
from src.config import config

# Karakter yang disamakan menjadi spasi agar "push-up", "push up", dan
# "push_up" diperlakukan sebagai bentuk yang sama.
_PEMISAH = re.compile(r"[-\u2010\u2011\u2012\u2013\u2014_/]+")
_SPASI = re.compile(r"\s+")
# Bentuk rapat tanpa spasi juga umum ditulis pengguna maupun model.
_VARIAN_RAPAT = {"pushup": "push up", "pullup": "pull up", "chinup": "chin up"}


@dataclass
class ExerciseMedia:
    """Satu gerakan yang terdeteksi pada teks rencana."""

    id: str
    nama: str
    nama_id: str
    pola_gerak: str
    alat: str
    kelompok_otot_utama: list[str]
    kelompok_otot_pendukung: list[str]
    langkah: list[str]
    poin_kunci: str
    gambar: list[dict] = field(default_factory=list)
    sumber_media: dict = field(default_factory=dict)
    disebut_sebagai: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nama": self.nama,
            "nama_id": self.nama_id,
            "pola_gerak": self.pola_gerak,
            "alat": self.alat,
            "kelompok_otot_utama": self.kelompok_otot_utama,
            "kelompok_otot_pendukung": self.kelompok_otot_pendukung,
            "langkah": self.langkah,
            "poin_kunci": self.poin_kunci,
            "gambar": self.gambar,
            "sumber_media": self.sumber_media,
            "disebut_sebagai": self.disebut_sebagai,
        }


def normalisasi(teks: str) -> str:
    """Samakan bentuk penulisan sebelum pencocokan alias."""
    if not teks:
        return ""
    hasil = strip_source_markers(teks).lower()
    hasil = _PEMISAH.sub(" ", hasil)
    hasil = _SPASI.sub(" ", hasil)
    for rapat, renggang in _VARIAN_RAPAT.items():
        hasil = re.sub(rf"(?<![a-z0-9]){rapat}(?![a-z0-9])", renggang, hasil)
    return hasil


@lru_cache(maxsize=1)
def muat_katalog(path: str | None = None) -> dict:
    """Baca katalog gerakan sekali, lalu simpan di memori."""
    berkas = Path(path or config.EXERCISE_CATALOG_PATH)
    if not berkas.exists():
        return {"versi": 0, "gerakan": []}
    with open(berkas, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _pola_alias(path: str | None = None) -> tuple[re.Pattern | None, dict]:
    """Susun satu ekspresi reguler gabungan dari seluruh alias katalog.

    Alias diurutkan dari yang terpanjang agar "romanian deadlift" menang
    atas "deadlift" ketika keduanya cocok pada posisi yang sama.
    """
    katalog = muat_katalog(path)
    pemilik: dict[str, str] = {}
    for entri in katalog.get("gerakan", []):
        for alias in entri.get("alias", []):
            pemilik.setdefault(normalisasi(alias), entri["id"])

    if not pemilik:
        return None, {}

    alternatif = sorted(pemilik, key=len, reverse=True)
    pola = re.compile(
        r"(?<![a-z0-9])(?:" + "|".join(re.escape(a) for a in alternatif) + r")(?![a-z0-9])"
    )
    return pola, pemilik


def deteksi_gerakan(teks: str, path: str | None = None) -> list[tuple[str, str]]:
    """Kembalikan pasangan (id gerakan, alias yang tertulis) sesuai urutan muncul."""
    pola, pemilik = _pola_alias(path)
    if pola is None or not teks:
        return []

    ditemukan: list[tuple[str, str]] = []
    sudah: set[str] = set()
    for cocok in pola.finditer(normalisasi(teks)):
        alias = cocok.group(0)
        gerakan_id = pemilik[alias]
        if gerakan_id in sudah:
            continue
        sudah.add(gerakan_id)
        ditemukan.append((gerakan_id, alias))
    return ditemukan


def _url_gambar(berkas: str, asal: str) -> str:
    """Pakai berkas lokal bila tersedia, jatuh ke sumber daring bila belum diunduh."""
    lokal = Path(config.EXERCISE_MEDIA_DIR) / berkas
    if lokal.exists():
        return f"{config.EXERCISE_MEDIA_URL_PREFIX}/{berkas}"
    return asal


def kumpulkan_media(
    teks: str,
    *,
    batas: int | None = None,
    path: str | None = None,
) -> list[ExerciseMedia]:
    """Ambil ilustrasi dan tata cara untuk gerakan yang disebut pada teks."""
    katalog = muat_katalog(path)
    berdasarkan_id = {e["id"]: e for e in katalog.get("gerakan", [])}
    batas = config.MAX_EXERCISE_MEDIA if batas is None else batas

    hasil: list[ExerciseMedia] = []
    for gerakan_id, alias in deteksi_gerakan(teks, path):
        entri = berdasarkan_id.get(gerakan_id)
        if entri is None:
            continue
        hasil.append(
            ExerciseMedia(
                id=entri["id"],
                nama=entri["nama"],
                nama_id=entri["nama_id"],
                pola_gerak=entri["pola_gerak"],
                alat=entri.get("alat", ""),
                kelompok_otot_utama=entri.get("kelompok_otot_utama", []),
                kelompok_otot_pendukung=entri.get("kelompok_otot_pendukung", []),
                langkah=entri.get("langkah", []),
                poin_kunci=entri.get("poin_kunci", ""),
                gambar=[
                    {
                        "url": _url_gambar(g["berkas"], g["asal"]),
                        "keterangan": g.get("keterangan", ""),
                    }
                    for g in entri.get("gambar", [])
                ],
                sumber_media=entri.get("sumber_media", {}),
                disebut_sebagai=alias,
            )
        )
        if batas and len(hasil) >= batas:
            break
    return hasil


def bersihkan_cache() -> None:
    """Kosongkan cache katalog, dipakai pengujian dan pemuatan ulang katalog."""
    muat_katalog.cache_clear()
    _pola_alias.cache_clear()


def ringkasan_katalog(path: str | None = None) -> dict:
    """Ringkasan isi katalog untuk kebutuhan antarmuka dan lampiran skripsi."""
    katalog = muat_katalog(path)
    gerakan = katalog.get("gerakan", [])
    pola: dict[str, int] = {}
    for entri in gerakan:
        pola[entri["pola_gerak"]] = pola.get(entri["pola_gerak"], 0) + 1
    return {
        "total_gerakan": len(gerakan),
        "total_gambar": sum(len(e.get("gambar", [])) for e in gerakan),
        "total_alias": sum(len(e.get("alias", [])) for e in gerakan),
        "pola_gerak": pola,
        "lisensi_media": katalog.get("lisensi_media", ""),
        "sumber_media": katalog.get("sumber_media", ""),
    }
