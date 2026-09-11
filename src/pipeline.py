"""Orkestrasi alur lengkap sistem: dialogue analyzer, retrieval, plan generator, compliance checker."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable

from src.retriever import (
    Retriever,
    RetrievedDocument,
    format_full_documents_for_prompt,
)
from src.citations import build_citation_map, count_sentences_with_marker
from src.config import config
from src.exercise_media import ExerciseMedia, kumpulkan_media
from src.generator import (
    analyze_dialogue,
    generate_plan,
    check_compliance,
    regenerate_plan_with_feedback,
    answer_followup,
)
from src.dialogue_state import (
    INITIAL_PROFILE,
    merge_profile,
    get_missing_fields,
    build_clarifying_question,
    build_confirmation_question,
    build_profile_summary,
    is_affirmative,
    is_negative,
)

@dataclass
class PipelineResult:
    user_message: str
    status: str
    extracted_profile: dict
    message: str | None = None
    retrieved_sources: list[str] = field(default_factory=list)
    retrieved_documents: list[RetrievedDocument] = field(default_factory=list)
    plan: str = ""
    compliance: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    marked_sentences: int = 0
    total_sentences: int = 0
    revision_attempts: int = 0
    exercises: list[ExerciseMedia] = field(default_factory=list)

class TrainingPlanPipeline:
    """Alur utama sistem, dengan seluruh ketergantungan Gemini disuntikkan lewat konstruktor agar dapat diuji secara luring."""

    def __init__(
        self,
        retriever: Retriever | None = None,
        *,
        analyze_fn: Callable[..., dict] = analyze_dialogue,
        generate_fn: Callable[[dict, str], str] = generate_plan,
        compliance_fn: Callable[[str, dict], dict] = check_compliance,
        revise_fn: Callable[[dict, str, str, list], str] = regenerate_plan_with_feedback,
        followup_fn: Callable[[dict, str, str, str], str] = answer_followup,
        media_fn: Callable[[str], list[ExerciseMedia]] = kumpulkan_media,
    ):
        self.retriever = retriever or Retriever()
        self._analyze = analyze_fn
        self._generate = generate_fn
        self._check_compliance = compliance_fn
        self._revise = revise_fn
        self._followup = followup_fn
        self._media = media_fn
        self.profile: dict = dict(INITIAL_PROFILE)
        self.plan_ready: bool = False
        self.awaiting_confirmation: bool = False
        self.last_context: str = ""
        self.last_plan: str = ""
        self.last_documents: list[RetrievedDocument] = []

    def reset(self) -> None:
        self.profile = dict(INITIAL_PROFILE)
        self.plan_ready = False
        self.awaiting_confirmation = False
        self.last_context = ""
        self.last_plan = ""
        self.last_documents = []

    def run(self, user_message: str) -> PipelineResult:
        warnings: list[str] = []

        if self.awaiting_confirmation and is_affirmative(user_message):
            self.awaiting_confirmation = False
            return self._build_plan(user_message)

        extracted = self._analyze(
            user_message,
            current_riwayat_cedera=self.profile.get("riwayat_cedera"),
        )

        profile_before = dict(self.profile)
        self.profile = merge_profile(self.profile, extracted)
        profile_changed = self.profile != profile_before

        missing = get_missing_fields(self.profile)
        if missing:
            self.awaiting_confirmation = False
            return PipelineResult(
                user_message=user_message,
                status="butuh_info",
                extracted_profile=self.profile,
                message=build_clarifying_question(self.profile, missing),
            )

        if self.awaiting_confirmation:
            if profile_changed:
                return PipelineResult(
                    user_message=user_message,
                    status="butuh_konfirmasi",
                    extracted_profile=self.profile,
                    message=(
                        "Sudah aku perbaiki. Sekarang jadi begini:\n\n"
                        f"{build_profile_summary(self.profile)}\n\n"
                        "Sudah benar? Kalau sudah, bilang 'ya' atau 'lanjut'."
                    ),
                )
            if is_negative(user_message):
                return PipelineResult(
                    user_message=user_message,
                    status="butuh_konfirmasi",
                    extracted_profile=self.profile,
                    message=(
                        "Baik, bagian mana yang perlu diperbaiki? Sebutkan saja "
                        "nilai yang benar, misalnya \"frekuensinya 4 hari\" atau "
                        "\"levelnya menengah\"."
                    ),
                )
            return PipelineResult(
                user_message=user_message,
                status="butuh_konfirmasi",
                extracted_profile=self.profile,
                message=(
                    "Maaf, aku belum menangkap maksudnya. Kalau data di atas "
                    "sudah benar, bilang 'ya'. Kalau ada yang keliru, sebutkan "
                    "nilai yang benar."
                ),
            )

        if not self.plan_ready:
            self.awaiting_confirmation = True
            return PipelineResult(
                user_message=user_message,
                status="butuh_konfirmasi",
                extracted_profile=self.profile,
                message=build_confirmation_question(self.profile),
            )

        if self.plan_ready and not profile_changed:
            answer = self._followup(
                self.profile, self.last_context, self.last_plan, user_message
            )
            sources = [d.source for d in self.last_documents]
            marked, total = count_sentences_with_marker(answer)
            return PipelineResult(
                user_message=user_message,
                status="jawaban_lanjutan",
                extracted_profile=self.profile,
                message=answer,
                retrieved_sources=sources,
                retrieved_documents=self.last_documents,
                citations=build_citation_map(answer, sources),
                marked_sentences=marked,
                total_sentences=total,
                exercises=self._media(answer),
            )

        self.awaiting_confirmation = True
        return PipelineResult(
            user_message=user_message,
            status="butuh_konfirmasi",
            extracted_profile=self.profile,
            message=(
                "Profilnya berubah. Sekarang jadi begini:\n\n"
                f"{build_profile_summary(self.profile)}\n\n"
                "Sudah benar? Kalau sudah, bilang 'ya' supaya aku susun ulang "
                "rencananya."
            ),
        )

    def _build_plan(self, user_message: str) -> PipelineResult:
        warnings: list[str] = []
        query = self._build_retrieval_query(self.profile)
        retrieved_docs = self.retriever.retrieve_full_documents(query)

        if not retrieved_docs:
            warnings.append(
                "Nggak ada dokumen relevan ditemukan di knowledge base — "
                "pastikan sudah menjalankan ingest.py dan pertanyaan sesuai topik KB."
            )

        context = format_full_documents_for_prompt(retrieved_docs)

        plan = self._generate(self.profile, context)

        constraints = {"riwayat_cedera": self.profile.get("riwayat_cedera") or []}
        compliance = self._check_compliance(plan, constraints)

        revisions = 0
        while (
            not compliance.get("patuh", True)
            and revisions < config.COMPLIANCE_MAX_REVISIONS
        ):
            violations = compliance.get("pelanggaran") or []
            plan = self._revise(self.profile, context, plan, violations)
            revisions += 1
            compliance = self._check_compliance(plan, constraints)

        if not compliance.get("patuh", True):
            warnings.append(
                f"Rencana masih melanggar constraint setelah {revisions} kali "
                f"penyusunan ulang: {compliance.get('pelanggaran')}"
            )
        elif revisions:
            warnings.append(
                f"Rencana disusun ulang {revisions} kali untuk memenuhi batasan "
                f"riwayat cedera."
            )

        sources = [d.source for d in retrieved_docs]
        marked, total = count_sentences_with_marker(plan)

        # Pemetaan ilustrasi dijalankan paling akhir, atas rencana yang sudah
        # lolos compliance checker, sehingga gerakan yang sempat ditolak pada
        # tahap revisi tidak ikut ditampilkan gambarnya. Daftar kosong bukan
        # kondisi galat: rencana boleh saja hanya menyebut pola gerak umum.
        exercises = self._media(plan)

        self.plan_ready = True
        self.last_context = context
        self.last_plan = plan
        self.last_documents = retrieved_docs

        return PipelineResult(
            user_message=user_message,
            status="rencana_siap",
            extracted_profile=self.profile,
            retrieved_sources=[d.source for d in retrieved_docs],
            retrieved_documents=retrieved_docs,
            plan=plan,
            compliance=compliance,
            warnings=warnings,
            citations=build_citation_map(plan, sources),
            marked_sentences=marked,
            total_sentences=total,
            revision_attempts=revisions,
            exercises=exercises,
        )

    @staticmethod
    def _build_retrieval_query(profile: dict) -> str:
        parts = [profile.get("tujuan_latihan", "")]
        cedera = profile.get("riwayat_cedera") or []
        if cedera:
            parts.append("cedera: " + ", ".join(cedera))
        level = profile.get("level_pengalaman")
        if level and level != "tidak_disebutkan":
            parts.append(f"level {level}")
        return " ".join(p for p in parts if p)
