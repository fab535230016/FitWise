"""Antarmuka web untuk pipeline penyusun rencana latihan."""

from __future__ import annotations
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import config, validate_config
from src.dialogue_state import FIELD_LABELS, REQUIRED_FIELDS, format_field
from src.exercise_media import ringkasan_katalog
from web.feedback import FeedbackStore
from web.session import SessionStore

STATIC_DIR = Path(__file__).resolve().parent / "static"

state: dict = {
    "store": None,
    "ready": False,
    "error": None,
    "chunks": 0,
    "feedback": None,
}


def default_pipeline_factory():
    from src.pipeline import TrainingPlanPipeline

    return TrainingPlanPipeline(retriever=state["retriever"])


def warm_up() -> None:
    """Muat model embedding dan hitung isi basis pengetahuan satu kali di awal."""
    from src.retriever import Retriever

    retriever = Retriever()
    retriever._ensure_model_loaded()
    state["retriever"] = retriever
    state["chunks"] = retriever.collection_count()
    state["ready"] = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    for warning in validate_config():
        print(f"Peringatan: {warning}")

    if state["feedback"] is None:
        state["feedback"] = FeedbackStore(config.FEEDBACK_PATH)

    if state["store"] is None:
        try:
            warm_up()
            state["store"] = SessionStore(default_pipeline_factory)
            print(f"Siap. Basis pengetahuan memuat {state['chunks']} potongan.")
        except Exception as e:
            state["error"] = str(e)
            print(f"Gagal menyiapkan retriever: {e}")
    yield


app = FastAPI(title="FitWise", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class ResetRequest(BaseModel):
    session_id: str | None = None


class FeedbackRequest(BaseModel):
    session_id: str = Field(min_length=1)
    rating: str = Field(pattern="^(berguna|tidak_berguna)$")
    reason: str = Field(default="", max_length=500)
    profile: dict = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)
    plan_excerpt: str = Field(default="", max_length=400)


def profile_rows(profile: dict) -> list[dict]:
    return [
        {"label": FIELD_LABELS[field], "value": format_field(profile, field)}
        for field in REQUIRED_FIELDS
    ]


def retrieval_rows(documents, preview_chars: int = 220) -> list[dict]:
    """Rangkum dokumen terambil beserta potongan yang memicunya."""
    rows = []
    for number, doc in enumerate(documents, start=1):
        rows.append({
            "marker": f"S{number}",
            "source": doc.source,
            "is_core": doc.is_core,
            "best_distance": (
                None if doc.best_distance is None else round(doc.best_distance, 4)
            ),
            "num_chunks": doc.num_chunks,
            "num_hit_chunks": doc.num_hit_chunks,
            "hit_previews": [
                chunk[:preview_chars].strip() for chunk in doc.hit_chunks[:3]
            ],
        })
    return rows


KATEGORI_DOKUMEN = {
    "american_college_of_sports_medicine_position": "Prinsip preskripsi latihan beban",
    "ijerph-19-12710": "Cedera umum di pusat kebugaran",
    "fbioe-13-1560597": "Nyeri bahu",
    "s13102-025-01297-x": "Nyeri lutut",
    "jcm-10-03968-v2": "Nyeri siku",
    "journal.pone.0262023": "Cedera pergelangan kaki",
    "s10926-023-10124-4": "Nyeri punggung bawah",
}


def kategori(source: str) -> str:
    nama = source.rsplit(".", 1)[0]
    for kunci, label in KATEGORI_DOKUMEN.items():
        if kunci in nama:
            return label
    return "Dokumen pendukung"


@app.get("/api/knowledge-base")
def knowledge_base():
    """Ringkasan isi basis pengetahuan untuk bagian sumber pada halaman."""
    if not state["ready"]:
        return JSONResponse(status_code=503, content={"error": "Sistem belum siap."})

    dokumen = state["retriever"].describe_documents()
    for d in dokumen:
        d["kategori"] = kategori(d["source"])
    return {
        "documents": dokumen,
        "total_documents": len(dokumen),
        "total_chunks": sum(d["num_chunks"] for d in dokumen),
        "total_characters": sum(d["characters"] for d in dokumen),
    }


@app.get("/api/katalog-gerakan")
def katalog_gerakan():
    """Ringkasan katalog ilustrasi gerakan beserta rujukan lisensinya."""
    return ringkasan_katalog()


@app.get("/api/health")
def health() -> dict:
    return {
        "ready": state["ready"],
        "chunks": state["chunks"],
        "error": state["error"],
        "sessions": state["store"].count() if state["store"] else 0,
    }


@app.post("/api/chat")
def chat(request: ChatRequest):
    if state["store"] is None:
        return JSONResponse(
            status_code=503,
            content={"error": state["error"] or "Sistem belum siap."},
        )

    session = state["store"].get_or_create(request.session_id)

    with session.lock:
        try:
            result = session.pipeline.run(request.message.strip())
        except Exception as e:
            filled = [
                f for f in REQUIRED_FIELDS
                if session.pipeline.profile.get(f) is not None
            ]
            return JSONResponse(
                status_code=502,
                content={
                    "session_id": session.session_id,
                    "error": str(e),
                    "filled_fields": len(filled),
                    "total_fields": len(REQUIRED_FIELDS),
                    "profile": profile_rows(session.pipeline.profile),
                },
            )

    plan_ready = result.status == "rencana_siap"
    return {
        "session_id": session.session_id,
        "status": result.status,
        "has_plan": plan_ready or result.status == "jawaban_lanjutan",
        "message": result.message,
        "plan": result.plan,
        "profile": profile_rows(result.extracted_profile),
        "sources": result.retrieved_sources,
        "citations": result.citations,
        "retrieval": retrieval_rows(result.retrieved_documents),
        "grounding": {
            "marked_sentences": result.marked_sentences,
            "total_sentences": result.total_sentences,
        },
        "revision_attempts": result.revision_attempts,
        "compliance": result.compliance,
        "warnings": result.warnings,
        "exercises": [e.to_dict() for e in result.exercises],
    }


@app.post("/api/reset")
def reset(request: ResetRequest):
    if state["store"] is None:
        return JSONResponse(status_code=503, content={"error": "Sistem belum siap."})

    session = state["store"].reset(request.session_id)
    return {"session_id": session.session_id, "status": "reset"}


@app.post("/api/feedback")
def feedback(request: FeedbackRequest):
    if state["feedback"] is None:
        return JSONResponse(status_code=503, content={"error": "Sistem belum siap."})

    entry = state["feedback"].record(
        session_id=request.session_id,
        rating=request.rating,
        reason=request.reason,
        profile=request.profile,
        sources=request.sources,
        plan_excerpt=request.plan_excerpt,
    )
    return {"status": "tersimpan", "waktu": entry["waktu"]}


@app.get("/api/feedback/summary")
def feedback_summary():
    if state["feedback"] is None:
        return JSONResponse(status_code=503, content={"error": "Sistem belum siap."})
    return state["feedback"].summary()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
