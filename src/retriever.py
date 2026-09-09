"""Modul retrieval: embed query, cari dokumen relevan di ChromaDB, rekonstruksi dokumen penuh."""

from __future__ import annotations
from dataclasses import dataclass, field

from src.config import config


@dataclass
class RetrievedChunk:
    text: str
    source: str
    distance: float
    metadata: dict


@dataclass
class RetrievedDocument:
    source: str
    full_text: str
    best_distance: float | None
    num_chunks: int
    num_hit_chunks: int
    is_core: bool
    hit_chunks: list[str] = field(default_factory=list)


class Retriever:
    def __init__(self, embedding_model=None):
        import chromadb

        self._model = embedding_model
        self._client = chromadb.PersistentClient(path=config.CHROMA_DB_PATH)
        self._collection = self._client.get_or_create_collection(name=config.COLLECTION_NAME)

    def _ensure_model_loaded(self):
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel
            self._model = BGEM3FlagModel(
                config.EMBEDDING_MODEL,
                use_fp16=config.EMBEDDING_USE_FP16,
                device=config.EMBEDDING_DEVICE,
            )

    def _embed_query(self, query: str) -> list[float]:
        self._ensure_model_loaded()
        output = self._model.encode(
            [query],
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return output["dense_vecs"][0].tolist()

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        top_k = top_k or config.TOP_K
        query_embedding = self._embed_query(query)

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )

        retrieved = []
        docs = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for text, meta, dist in zip(docs, metadatas, distances):
            retrieved.append(
                RetrievedChunk(
                    text=text,
                    source=meta.get("source", "unknown"),
                    distance=dist,
                    metadata=meta,
                )
            )
        return retrieved

    def _document_chunks(self, source: str) -> list[str]:
        result = self._collection.get(
            where={"source": source},
            include=["documents", "metadatas"],
        )
        pairs = list(zip(result["documents"], result["metadatas"]))
        pairs.sort(key=lambda p: p[1].get("chunk_index", 0))
        return [text for text, _ in pairs]

    def get_full_document(self, source: str) -> str:
        return "\n\n".join(self._document_chunks(source))

    def list_all_sources(self) -> list[str]:
        result = self._collection.get(include=["metadatas"])
        return sorted({m.get("source", "unknown") for m in result["metadatas"]})

    def _is_core_document(self, source: str) -> bool:
        source_lower = source.lower()
        return any(kw.lower() in source_lower for kw in config.CORE_DOCUMENT_KEYWORDS)

    def retrieve_full_documents(
        self,
        query: str,
        top_k_chunks: int | None = None,
        max_conditional_documents: int | None = None,
    ) -> list[RetrievedDocument]:
        top_k_chunks = top_k_chunks or config.TOP_K_CHUNKS_FOR_RANKING
        max_conditional_documents = (
            max_conditional_documents or config.MAX_CONDITIONAL_DOCUMENTS
        )

        all_sources = self.list_all_sources()
        core_sources = [s for s in all_sources if self._is_core_document(s)]

        chunk_hits = self.retrieve(query, top_k=top_k_chunks)

        best_distance_per_source: dict[str, float] = {}
        for c in chunk_hits:
            if c.source in core_sources:
                continue
            if c.source not in best_distance_per_source:
                best_distance_per_source[c.source] = c.distance

        ranked_sources = sorted(best_distance_per_source.items(), key=lambda kv: kv[1])
        top_conditional_sources = ranked_sources[:max_conditional_documents]

        final_sources = [(s, None) for s in core_sources] + [
            (s, d) for s, d in top_conditional_sources
        ]

        results = []
        for source, best_distance in final_sources:
            chunks = self._document_chunks(source)
            hits = [c for c in chunk_hits if c.source == source]
            hits.sort(key=lambda c: c.distance)
            results.append(
                RetrievedDocument(
                    source=source,
                    full_text="\n\n".join(chunks),
                    best_distance=best_distance,
                    num_chunks=len(chunks),
                    num_hit_chunks=len(hits),
                    is_core=source in core_sources,
                    hit_chunks=[c.text for c in hits],
                )
            )
        return results

    def describe_documents(self) -> list[dict]:
        """Ringkas isi basis pengetahuan untuk ditampilkan di antarmuka."""
        hasil = []
        for source in sorted(self.list_all_sources()):
            potongan = self._document_chunks(source)
            hasil.append({
                "source": source,
                "is_core": self._is_core_document(source),
                "num_chunks": len(potongan),
                "characters": sum(len(t) for t in potongan),
            })
        hasil.sort(key=lambda d: (not d["is_core"], -d["num_chunks"]))
        return hasil

    def collection_count(self) -> int:
        return self._collection.count()


def format_context_for_prompt(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        parts.append(f"[Sumber {i}: {c.source}]\n{c.text}")
    return "\n\n---\n\n".join(parts)


def format_full_documents_for_prompt(documents: list[RetrievedDocument]) -> str:
    parts = []
    for i, d in enumerate(documents, start=1):
        parts.append(f"[Sumber {i}: {d.source} -- dokumen lengkap]\n{d.full_text}")
    return "\n\n---\n\n".join(parts)


def collect_evaluation_contexts(
    documents: list[RetrievedDocument],
    mode: str | None = None,
    chunks_per_document: int | None = None,
) -> list[str]:
    """Susun konteks untuk penilai RAGAs sesuai EVAL_CONTEXT_MODE."""
    mode = mode or config.EVAL_CONTEXT_MODE
    n = chunks_per_document or config.EVAL_CHUNKS_PER_DOCUMENT

    if mode == "full_document":
        return [d.full_text for d in documents]

    if mode != "retrieved_chunks":
        raise ValueError(f"Mode konteks evaluasi tidak dikenal: {mode}")

    contexts: list[str] = []
    for d in documents:
        potongan = d.hit_chunks[:n]
        if not potongan:
            potongan = d.full_text.split("\n\n")[:n]
        for teks in potongan:
            if teks.strip():
                contexts.append(f"[{d.source}]\n{teks.strip()}")
    return contexts
