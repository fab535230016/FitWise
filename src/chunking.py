"""Utility untuk memecah dokumen panjang menjadi chunk siap embed."""

from __future__ import annotations
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    chunk_index: int
    source: str
    metadata: dict


def _split_into_paragraphs(text: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in paragraphs if p.strip()]


def _split_into_sentences(text: str) -> list[str]:
    sentence_endings = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
    sentences = sentence_endings.split(text)
    return [s.strip() for s in sentences if s.strip()]


def _hard_split(text: str, limit: int) -> list[str]:
    """Pecah paksa teks yang masih melebihi limit setelah dipecah per kalimat."""
    pieces: list[str] = []
    rest = text.strip()
    while len(rest) > limit:
        cut = rest.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        pieces.append(rest)
    return pieces


def chunk_text(
    text: str,
    source: str,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
    extra_metadata: dict | None = None,
) -> list[Chunk]:
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap harus lebih kecil dari chunk_size")

    paragraphs = _split_into_paragraphs(text)
    chunks: list[Chunk] = []
    current = ""

    def flush(current_text: str) -> None:
        if current_text.strip():
            chunks.append(
                Chunk(
                    text=current_text.strip(),
                    chunk_index=len(chunks),
                    source=source,
                    metadata=extra_metadata or {},
                )
            )

    budget = chunk_size - chunk_overlap - 2

    def units_of(block: str) -> list[str]:
        out: list[str] = []
        for sent in _split_into_sentences(block):
            if len(sent) > budget:
                out.extend(_hard_split(sent, budget))
            else:
                out.append(sent)
        return out

    def append_unit(unit: str, joiner: str) -> None:
        nonlocal current
        if not current:
            current = unit
            return
        if len(current) + len(joiner) + len(unit) <= chunk_size:
            current = f"{current}{joiner}{unit}"
            return
        flush(current)
        overlap_text = current[-chunk_overlap:]
        current = f"{overlap_text}{joiner}{unit}".strip()

    for para in paragraphs:
        if len(para) > budget:
            for unit in units_of(para):
                append_unit(unit, " ")
            continue
        append_unit(para, "\n\n")

    flush(current)
    return chunks


def chunk_file(
    filepath: str,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
    extra_metadata: dict | None = None,
) -> list[Chunk]:
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    source = filepath.split("/")[-1]
    return chunk_text(text, source, chunk_size, chunk_overlap, extra_metadata)
