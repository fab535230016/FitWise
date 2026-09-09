"""Konfigurasi terpusat untuk RAG pipeline."""

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent

VALID_ARMS = ("rag", "baseline", "context_only", "instruction_only")
VALID_CONTEXT_MODES = ("full_document", "retrieved_chunks")

ARM_DESIGN: dict[str, tuple[bool, bool]] = {
    "rag": (True, True),
    "baseline": (False, False),
    "context_only": (True, False),
    "instruction_only": (False, True),
}


@dataclass
class Config:
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DEVICE: str = "cpu"
    EMBEDDING_USE_FP16: bool = False

    CHROMA_DB_PATH: str = str(BASE_DIR / "data" / "chroma_db")
    COLLECTION_NAME: str = "sports_science_kb"
    KNOWLEDGE_BASE_DIR: str = str(BASE_DIR / "data" / "knowledge_base")
    FEEDBACK_PATH: str = str(BASE_DIR / "data" / "feedback.jsonl")

    GEMINI_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_FALLBACK_MODEL: str | None = None
    EVAL_JUDGE_MODEL: str | None = None
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 150
    DROP_REFERENCE_CHUNKS: bool = True

    TOP_K: int = 5
    TOP_K_CHUNKS_FOR_RANKING: int = 10
    MAX_CONDITIONAL_DOCUMENTS: int = 4
    CORE_DOCUMENT_KEYWORDS: tuple[str, ...] = (
        "acsm",
        "sports_medicine_position",
        "currier",
        "prinsip_dasar_rt",
    )

    COMPLIANCE_MAX_REVISIONS: int = 2

    DIALOGUE_TEMPERATURE: float = 0.1
    GENERATION_TEMPERATURE: float = 0.2
    COMPLIANCE_TEMPERATURE: float = 0.0
    GENERATION_SEED: int | None = 42

    RETRY_MAX_ATTEMPTS: int = 4
    RETRY_BASE_DELAY_SECONDS: float = 2.0
    RETRY_MAX_DELAY_SECONDS: float = 30.0
    API_PACING_DELAY_SECONDS: int = 30

    EVAL_ARMS: tuple[str, ...] = ("rag", "baseline", "context_only")
    EVAL_CONTEXT_MODE: str = "full_document"
    EVAL_CHUNKS_PER_DOCUMENT: int = 8
    EVAL_SCENARIO_LIMIT: int | None = None

    @property
    def MAX_DOCUMENTS(self) -> int:
        return self.MAX_CONDITIONAL_DOCUMENTS


config = Config()


def validate_config() -> list[str]:
    """Kumpulkan peringatan konfigurasi tanpa menghentikan program."""
    warnings = []

    if not config.GEMINI_API_KEY:
        warnings.append(
            "GEMINI_API_KEY belum diset. Buat file .env (copy dari .env.example) "
            "dan isi API key dari https://aistudio.google.com/apikey"
        )

    if not Path(config.KNOWLEDGE_BASE_DIR).exists():
        warnings.append(f"Folder knowledge base belum ada: {config.KNOWLEDGE_BASE_DIR}")

    unknown_arms = [a for a in config.EVAL_ARMS if a not in VALID_ARMS]
    if unknown_arms:
        warnings.append(
            f"EVAL_ARMS memuat lengan yang tidak dikenal: {unknown_arms}. "
            f"Pilihan yang sah: {list(VALID_ARMS)}"
        )

    if "rag" not in config.EVAL_ARMS:
        warnings.append("EVAL_ARMS tidak memuat 'rag', tidak ada yang bisa dibandingkan.")

    if config.EVAL_CONTEXT_MODE not in VALID_CONTEXT_MODES:
        warnings.append(
            f"EVAL_CONTEXT_MODE tidak dikenal: {config.EVAL_CONTEXT_MODE}. "
            f"Pilihan yang sah: {list(VALID_CONTEXT_MODES)}"
        )

    return warnings
