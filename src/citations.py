"""Penanda sumber pada rencana latihan dan pemetaannya ke dokumen."""

from __future__ import annotations
import re

MARKER_PATTERN = re.compile(r"\[S\d{1,2}(?:\s*,\s*S?\d{1,2})*\]")


def marker_numbers(marker: str) -> list[int]:
    """Nomor sumber pada satu penanda, termasuk penanda gabungan seperti [S1, S3]."""
    return [int(n) for n in re.findall(r"\d{1,2}", marker)]


def strip_source_markers(text: str) -> str:
    """Buang penanda sumber agar teks dapat dinilai setara dengan lengan lain."""
    if not text:
        return text
    cleaned = MARKER_PATTERN.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    return cleaned.strip()


def used_marker_numbers(text: str) -> list[int]:
    """Nomor sumber yang muncul pada teks, urut dan tanpa pengulangan."""
    if not text:
        return []
    return sorted({n for m in MARKER_PATTERN.findall(text) for n in marker_numbers(m)})


def build_citation_map(plan: str, sources: list[str]) -> list[dict]:
    """Petakan setiap penanda yang dipakai ke nama berkas sumbernya."""
    citations = []
    for number in used_marker_numbers(plan):
        index = number - 1
        citations.append({
            "marker": f"S{number}",
            "number": number,
            "source": sources[index] if 0 <= index < len(sources) else None,
            "valid": 0 <= index < len(sources),
        })
    return citations


def count_sentences_with_marker(plan: str,
                                sources: list[str] | None = None) -> tuple[int, int]:
    """Hitung kalimat bertanda sumber sah dibanding seluruh kalimat isi.

    Baris yang hanya berisi judul atau penutup singkat diabaikan agar
    rasionya mencerminkan kalimat rekomendasi, bukan sapaan.

    Bila daftar sumber diberikan, penanda di luar jangkauan seperti [S7]
    saat hanya tiga dokumen terambil tidak dihitung sebagai bersumber.
    Tanpa daftar sumber, seluruh penanda dianggap sah.
    """
    if not plan:
        return 0, 0
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", plan) if len(s.strip()) > 25]

    def bersumber(kalimat: str) -> bool:
        nomor = [n for m in MARKER_PATTERN.findall(kalimat) for n in marker_numbers(m)]
        if not nomor:
            return False
        if sources is None:
            return True
        return any(1 <= n <= len(sources) for n in nomor)

    return sum(1 for s in sentences if bersumber(s)), len(sentences)
