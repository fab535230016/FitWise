"""Pipeline ingest: baca dokumen dari data/knowledge_base, chunk, embed dengan BGE-M3, simpan ke ChromaDB."""

from __future__ import annotations
import os
import re
from pathlib import Path

import chromadb
from pypdf import PdfReader

from src.config import config
from src.chunking import chunk_text, Chunk

from FlagEmbedding import BGEM3FlagModel


def load_embedding_model() -> BGEM3FlagModel:
    print(f"[ingest] Loading embedding model: {config.EMBEDDING_MODEL} ...")
    model = BGEM3FlagModel(
        config.EMBEDDING_MODEL,
        use_fp16=config.EMBEDDING_USE_FP16,
        device=config.EMBEDDING_DEVICE,
    )
    print("[ingest] Model loaded.")
    return model


def embed_texts(model: BGEM3FlagModel, texts: list[str]) -> list[list[float]]:
    output = model.encode(
        texts,
        batch_size=8,
        max_length=1024,
        return_dense=True,
        return_sparse=False,
        return_colbert_vecs=False,
    )
    return output["dense_vecs"].tolist()


def extract_text_from_pdf(filepath: str) -> str:
    reader = PdfReader(filepath)
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def load_documents_from_dir(directory: str) -> list[tuple[str, str]]:
    docs = []
    for path in Path(directory).glob("*"):
        if path.suffix.lower() == ".txt":
            docs.append((path.name, path.read_text(encoding="utf-8")))
        elif path.suffix.lower() == ".pdf":
            text = extract_text_from_pdf(str(path))
            chars_per_page = len(text) / max(path_page_count(str(path)), 1)
            if len(text.strip()) < 500 or chars_per_page < 200:
                print(
                    f"[ingest] Peringatan: {path.name} cuma ke-extract {len(text.strip())} "
                    f"karakter -- kemungkinan besar ini PDF hasil scan gambar "
                    f"(image-only), bukan PDF teks asli. pypdf nggak bisa baca "
                    f"gambar; perlu OCR (mis. dengan ocrmypdf) sebelum ingest, "
                    f"atau cari versi PDF lain dari sumber yang sama."
                )
            docs.append((path.name, text))
    return docs


def path_page_count(filepath: str) -> int:
    try:
        return len(PdfReader(filepath).pages)
    except Exception:
        return 1


_REF_NUMBERED = re.compile(r"(?m)(?:^|\s)\d{1,3}\.\s+[A-Z][a-z]+")
_REF_BRACKET = re.compile(r"\[\d{1,3}\]")
_REF_JOURNAL = re.compile(r"(?i)\b(?:19|20)\d{2};\d+")
_REF_MARKER = re.compile(r"(?i)doi|crossref|pubmed")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def looks_like_reference_block(text: str) -> bool:
    """Tebak apakah sebuah chunk berisi daftar pustaka atau boilerplate jurnal."""
    if len(_REF_NUMBERED.findall(text)) >= 3:
        return True
    if len(_REF_BRACKET.findall(text)) >= 3:
        return True
    if len(_REF_JOURNAL.findall(text)) >= 2:
        return True
    if len(_REF_MARKER.findall(text)) >= 2 and len(_YEAR.findall(text)) >= 3:
        return True
    return False


def build_chunks_from_directory(directory: str) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    docs = load_documents_from_dir(directory)
    if not docs:
        print(f"[ingest] Nggak ada file .txt/.pdf ditemukan di {directory}")
        return all_chunks

    for filename, text in docs:
        doc_chunks = chunk_text(
            text,
            source=filename,
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )

        dropped = 0
        if config.DROP_REFERENCE_CHUNKS:
            kept = [c for c in doc_chunks if not looks_like_reference_block(c.text)]
            dropped = len(doc_chunks) - len(kept)
            for new_index, c in enumerate(kept):
                c.chunk_index = new_index
            doc_chunks = kept

        oversize = sum(1 for c in doc_chunks if len(c.text) > config.CHUNK_SIZE)
        note = f"{len(doc_chunks)} chunk"
        if dropped:
            note += f" ({dropped} chunk daftar pustaka dibuang)"
        if oversize:
            note += f" -- PERINGATAN: {oversize} chunk melebihi {config.CHUNK_SIZE} karakter"
        print(f"[ingest] {filename}: {note}")

        all_chunks.extend(doc_chunks)
    return all_chunks


def ingest(directory: str | None = None) -> None:
    directory = directory or config.KNOWLEDGE_BASE_DIR

    chunks = build_chunks_from_directory(directory)
    if not chunks:
        print("[ingest] Nggak ada chunk buat di-ingest. Berhenti.")
        return

    model = load_embedding_model()
    texts = [c.text for c in chunks]

    print(f"[ingest] Embedding {len(texts)} chunk...")
    embeddings = embed_texts(model, texts)

    client = chromadb.PersistentClient(path=config.CHROMA_DB_PATH)
    collection = client.get_or_create_collection(name=config.COLLECTION_NAME)

    ids = [f"{c.source}::chunk_{c.chunk_index}" for c in chunks]
    metadatas = [{"source": c.source, "chunk_index": c.chunk_index, **c.metadata} for c in chunks]

    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    print(f"[ingest] Selesai. {len(chunks)} chunk tersimpan di collection '{config.COLLECTION_NAME}'.")
    print(f"[ingest] Lokasi DB: {config.CHROMA_DB_PATH}")


if __name__ == "__main__":
    ingest()
