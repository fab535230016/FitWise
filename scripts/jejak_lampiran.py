"""Jejak perhitungan Lampiran 1 dengan kode FitWise terbaru.

Skrip ini menjalankan pesan contoh Lampiran 1 lewat pipeline yang sebenarnya
(Dialogue Analyzer, Retrieval, Plan Generator, Compliance Checker), lalu
mencatat setiap nilai antara yang dipakai pada Lampiran 1:

  evaluation/results/jejak_lampiran.json        seluruh nilai antara
  evaluation/results/jejak_lampiran_vektor.csv  vektor kueri dan sepuluh potongan terdekat

Tidak ada berkas program yang diubah. Jalankan dari folder proyek:

  python -m scripts.jejak_lampiran
"""

from __future__ import annotations
import asyncio
import csv
import json
import re
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import evaluation.run_eval as RE
from src.config import config
from src import generator as G
from src.pipeline import TrainingPlanPipeline
from src.retriever import Retriever, format_full_documents_for_prompt
from src.citations import (
    MARKER_PATTERN,
    build_citation_map,
    count_sentences_with_marker,
    marker_numbers,
    strip_source_markers,
    used_marker_numbers,
)
from src.dialogue_state import get_missing_fields
from src.exercise_media import deteksi_gerakan, kumpulkan_media
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import Faithfulness, ResponseGroundedness

PESAN = [
    "Saya mau latihan beban tapi gak tau mulai darimana, saya masih pemula tapi "
    "pengen nambah otot, bisa latihan 3 kali seminggu dan untuk cedera tidak ada.",
    "umur saya 21 tahun",
    "ya",
]
OUT_DIR = ROOT / "evaluation" / "results"
JEDA_ANTAR_PANGGILAN = 5

catatan: dict = {"dijalankan_pada": datetime.now().isoformat(timespec="seconds")}
galat: list[str] = []


def simpan() -> None:
    catatan["galat"] = galat
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "jejak_lampiran.json"
    path.write_text(json.dumps(catatan, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nTersimpan: {path}")


def bagian(nama: str):
    """Dekorator kecil: galat pada satu bagian dicatat tanpa menghentikan bagian lain."""
    def bungkus(fn):
        def jalan(*a, **k):
            try:
                return fn(*a, **k)
            except Exception as e:
                galat.append(f"{nama}: {type(e).__name__}: {e}\n{traceback.format_exc()}")
                print(f"  [galat] {nama}: {e}")
                return None
        return jalan
    return bungkus


def catat_konfigurasi() -> None:
    nama = [
        "EMBEDDING_MODEL", "CHUNK_SIZE", "CHUNK_OVERLAP", "DROP_REFERENCE_CHUNKS",
        "TOP_K_CHUNKS_FOR_RANKING", "MAX_CONDITIONAL_DOCUMENTS", "CORE_DOCUMENT_KEYWORDS",
        "USIA_MINIMUM", "COMPLIANCE_MAX_REVISIONS", "DIALOGUE_TEMPERATURE",
        "GENERATION_TEMPERATURE", "COMPLIANCE_TEMPERATURE", "GENERATION_SEED",
        "RETRY_MAX_ATTEMPTS", "RETRY_BASE_DELAY_SECONDS", "RETRY_MAX_DELAY_SECONDS",
        "RETRY_ATTEMPTS_INTERAKTIF", "RETRY_DELAY_INTERAKTIF_SECONDS",
        "API_PACING_DELAY_SECONDS", "MAX_EXERCISE_MEDIA", "GEMINI_MODEL",
        "GEMINI_FALLBACK_MODEL", "EVAL_CONTEXT_MODE",
    ]
    catatan["konfigurasi"] = {n: getattr(config, n) for n in nama}
    try:
        catatan["sidik_kode"] = RE.sidik_kode()
    except Exception as e:
        catatan["sidik_kode"] = f"gagal: {e}"
    try:
        catatan["git_status"] = subprocess.run(
            ["git", "status", "--porcelain", "--", "src", "web", "evaluation", "main.py"],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        ).stdout.splitlines()
    except Exception:
        pass


log_gemini: dict = {"analyze": [], "generate": [], "compliance": [], "revise": []}


def analyze_tercatat(pesan, current_riwayat_cedera=None):
    hasil = G.analyze_dialogue(pesan, current_riwayat_cedera=current_riwayat_cedera)
    log_gemini["analyze"].append({"pesan": pesan, "riwayat_cedera_sebelumnya": current_riwayat_cedera,
                                  "hasil": hasil})
    return hasil


def generate_tercatat(profil, konteks):
    rencana = G.generate_plan(profil, konteks)
    log_gemini["generate"].append({"profil": dict(profil), "panjang_konteks": len(konteks), "rencana": rencana})
    return rencana


def compliance_tercatat(rencana, batasan):
    hasil = G.check_compliance(rencana, batasan)
    log_gemini["compliance"].append({"batasan": batasan, "hasil": hasil})
    return hasil


def revise_tercatat(profil, konteks, rencana, pelanggaran):
    baru = G.regenerate_plan_with_feedback(profil, konteks, rencana, pelanggaran)
    log_gemini["revise"].append({"pelanggaran": pelanggaran, "rencana_baru": baru})
    return baru


@bagian("basis_pengetahuan")
def catat_basis(retriever: Retriever) -> None:
    dokumen = retriever.describe_documents()
    for d in dokumen:
        d["kata_kunci_inti"] = [k for k in config.CORE_DOCUMENT_KEYWORDS if k.lower() in d["source"].lower()]
    catatan["basis_pengetahuan"] = {
        "jumlah_potongan": retriever.collection_count(),
        "jumlah_dokumen": len(dokumen),
        "dokumen": dokumen,
    }


@bagian("retrieval")
def catat_retrieval(retriever: Retriever, kueri: str) -> None:
    q = retriever._embed_query(kueri)
    hasil = retriever._collection.query(
        query_embeddings=[q], n_results=config.TOP_K_CHUNKS_FOR_RANKING,
        include=["documents", "metadatas", "distances", "embeddings"],
    )
    hits = []
    vektor = []
    for rank, (teks, meta, jarak, emb) in enumerate(zip(
            hasil["documents"][0], hasil["metadatas"][0], hasil["distances"][0], hasil["embeddings"][0]), 1):
        emb = [float(x) for x in emb]
        hits.append({
            "peringkat": rank, "source": meta.get("source"), "chunk_index": meta.get("chunk_index"),
            "jarak": float(jarak), "kosinus": sum(a * b for a, b in zip(q, emb)),
            "norma_kuadrat_v": sum(x * x for x in emb), "panjang_teks": len(teks), "awal_teks": teks[:200],
        })
        vektor.append(emb)
    catatan["retrieval"] = {
        "kueri": kueri,
        "norma_kuadrat_q": sum(x * x for x in q),
        "q_empat_pertama": q[:4], "q_dua_terakhir": q[-2:],
        "sepuluh_potongan": hits,
    }
    with open(OUT_DIR / "jejak_lampiran_vektor.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["j", "q"] + [f"v{i}" for i in range(1, len(vektor) + 1)])
        for j in range(len(q)):
            w.writerow([j + 1, repr(float(q[j]))] + [repr(v[j]) for v in vektor])


@bagian("dokumen_terpilih")
def catat_dokumen(retriever: Retriever, dokumen) -> None:
    rows = []
    for i, d in enumerate(dokumen, 1):
        potongan = retriever._document_chunks(d.source)
        rows.append({
            "penanda": f"S{i}", "source": d.source, "inti": d.is_core, "jarak_terkecil": d.best_distance,
            "jumlah_potongan": d.num_chunks, "potongan_masuk_10_teratas": d.num_hit_chunks,
            "jumlah_panjang_potongan": sum(len(p) for p in potongan),
            "panjang_teks_utuh": len(d.full_text),
            "awal_potongan_pemicu": [h[:200] for h in d.hit_chunks[:3]],
        })
    catatan["dokumen_terpilih"] = rows


@bagian("prompt")
def catat_prompt(profil: dict, dokumen) -> None:
    konteks = format_full_documents_for_prompt(dokumen)
    judul = [f"[Sumber {i}: {d.source} -- dokumen lengkap]\n" for i, d in enumerate(dokumen, 1)]
    prompt = G.build_plan_prompt(profil, konteks, use_context=True, use_grounding_instructions=True)
    kepala = G.PROMPT_HEADER.format(user_profile=json.dumps(profil, ensure_ascii=False, indent=2))
    blok = G.CONTEXT_BLOCK.format(context=konteks)
    aturan = re.findall(r"^\s*(\d+)\.", G.TASK_GROUNDED, re.M)
    catatan["prompt"] = {
        "panjang_konteks_terformat": len(konteks),
        "panjang_judul_sumber": [len(j) for j in judul],
        "jumlah_pemisah_antarsumber": max(len(dokumen) - 1, 0), "panjang_pemisah": len("\n\n---\n\n"),
        "panjang_kepala_prompt": len(kepala), "panjang_blok_konteks": len(blok),
        "tambahan_blok_konteks": len(blok) - len(konteks),
        "panjang_task_grounded": len(G.TASK_GROUNDED), "jumlah_aturan_task_grounded": len(aturan),
        "panjang_style_rules": len(G.STYLE_RULES), "panjang_prompt_total": len(prompt),
        "perkiraan_token_total": round(len(prompt) / 4),
        "kepala_prompt": kepala,
    }


@bagian("rencana")
def catat_rencana(rencana: str, sumber: list[str]) -> None:
    kalimat = [s.strip() for s in re.split(r"(?<=[.!?])\s+", rencana) if s.strip()]
    rinci = []
    for i, k in enumerate(kalimat, 1):
        nomor = [n for m in MARKER_PATTERN.findall(k) for n in marker_numbers(m)]
        rinci.append({
            "kalimat": f"K{i}", "panjang": len(k), "dihitung": len(k) > 25,
            "penanda": MARKER_PATTERN.findall(k),
            "berpenanda_sah": len(k) > 25 and any(1 <= n <= len(sumber) for n in nomor),
            "teks": k,
        })
    marked, total = count_sentences_with_marker(rencana, sumber)
    catatan["rencana"] = {
        "teks": rencana,
        "penanda_muncul": dict(Counter(MARKER_PATTERN.findall(rencana))),
        "nomor_unik": used_marker_numbers(rencana),
        "peta_sitasi": build_citation_map(rencana, sumber),
        "kalimat": rinci,
        "marked_sentences": marked, "total_sentences": total,
        "rasio": (marked / total) if total else None,
        "teks_tanpa_penanda": strip_source_markers(rencana),
    }


@bagian("gerakan")
def catat_gerakan(rencana: str) -> None:
    media = kumpulkan_media(rencana)
    catatan["gerakan"] = {
        "terdeteksi": [{"id": g, "alias": a} for g, a in deteksi_gerakan(rencana)],
        "ditampilkan": [{"id": m.id, "nama": m.nama, "nama_id": m.nama_id, "disebut_sebagai": m.disebut_sebagai}
                        for m in media],
    }


async def catat_ragas(profil: dict, rencana: str, dokumen) -> None:
    try:
        penilai = RE.build_evaluator_llm()
        keluaran_mentah: list[str] = []
        asli = penilai.agenerate_text

        async def tercatat(*a, **k):
            r = await asli(*a, **k)
            keluaran_mentah.append(r.generations[0][0].text)
            return r

        try:
            penilai.agenerate_text = tercatat
        except Exception:
            pass

        sampel = SingleTurnSample(
            user_input=RE.pertanyaan_penilai(profil),
            response=strip_source_markers(rencana),
            retrieved_contexts=[d.full_text for d in dokumen],
        )
        baris = sampel.to_dict()
        f = Faithfulness(llm=penilai)
        pernyataan = (await f._create_statements(baris, None)).statements
        await asyncio.sleep(config.API_PACING_DELAY_SECONDS)
        putusan = await f._create_verdicts(baris, pernyataan, None)
        skor_f = f._compute_score(putusan)
        await asyncio.sleep(config.API_PACING_DELAY_SECONDS)
        keluaran_mentah.clear()
        skor_g = await ResponseGroundedness(llm=penilai).single_turn_ascore(sampel)
        catatan["ragas"] = {
            "pertanyaan_penilai": sampel.user_input,
            "panjang_konteks_penilai": len("\n".join(sampel.retrieved_contexts)),
            "faithfulness": float(skor_f),
            "pernyataan": [{"pernyataan": p.statement, "putusan": p.verdict, "alasan": p.reason}
                           for p in putusan.statements],
            "groundedness": float(skor_g),
            "keluaran_mentah_groundedness": list(keluaran_mentah),
        }
    except Exception as e:
        galat.append(f"ragas: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        print(f"  [galat] ragas: {e}")


def main() -> None:
    config.GEMINI_FALLBACK_MODEL = None
    catat_konfigurasi()

    print("Memuat model BGE-M3 dan ChromaDB...")
    retriever = Retriever()
    retriever._ensure_model_loaded()
    catat_basis(retriever)

    pipeline = TrainingPlanPipeline(
        retriever=retriever, analyze_fn=analyze_tercatat, generate_fn=generate_tercatat,
        compliance_fn=compliance_tercatat, revise_fn=revise_tercatat,
    )

    giliran = []
    hasil = None
    for i, pesan in enumerate(PESAN, 1):
        print(f"Giliran {i}: {pesan}")
        hasil = pipeline.run(pesan)
        giliran.append({
            "giliran": i, "pesan": pesan, "status": hasil.status, "balasan": hasil.message,
            "profil": dict(pipeline.profile), "slot_kosong": get_missing_fields(pipeline.profile),
            "menunggu_konfirmasi": pipeline.awaiting_confirmation,
        })
        print(f"  status: {hasil.status}")
        catatan["giliran"] = giliran
        catatan["log_gemini"] = log_gemini
        simpan()
        if hasil.status == "rencana_siap":
            break
        time.sleep(JEDA_ANTAR_PANGGILAN)

    if hasil is None or hasil.status != "rencana_siap":
        galat.append("Rencana belum terbentuk; lihat bagian giliran.")
        simpan()
        return

    kueri = TrainingPlanPipeline._build_retrieval_query(pipeline.profile)
    catatan["hasil_akhir"] = {
        "kueri": kueri, "status": hasil.status, "retrieved_sources": hasil.retrieved_sources,
        "compliance": hasil.compliance, "revision_attempts": hasil.revision_attempts,
        "warnings": hasil.warnings, "citations": hasil.citations,
        "marked_sentences": hasil.marked_sentences, "total_sentences": hasil.total_sentences,
        "jumlah_gerakan": len(hasil.exercises),
    }
    catat_retrieval(retriever, kueri)
    catat_dokumen(retriever, hasil.retrieved_documents)
    catat_prompt(pipeline.profile, hasil.retrieved_documents)
    catat_rencana(hasil.plan, hasil.retrieved_sources)
    catat_gerakan(hasil.plan)
    simpan()

    print("Menghitung Faithfulness dan Groundedness untuk rencana contoh (beberapa menit)...")
    asyncio.run(catat_ragas(pipeline.profile, hasil.plan, hasil.retrieved_documents))
    simpan()

    r = catatan.get("retrieval", {})
    print("\nRingkasan")
    print(f"  kueri              : {kueri}")
    print(f"  dokumen terpilih   : {hasil.retrieved_sources}")
    print(f"  kalimat bersumber  : {hasil.marked_sentences}/{hasil.total_sentences}")
    print(f"  gerakan            : {len(hasil.exercises)}")
    if "ragas" in catatan:
        print(f"  faithfulness       : {catatan['ragas']['faithfulness']:.4f}")
        print(f"  groundedness       : {catatan['ragas']['groundedness']:.4f}")
    if galat:
        print(f"  ada {len(galat)} galat, lihat bagian 'galat' pada berkas JSON")


if __name__ == "__main__":
    try:
        main()
    finally:
        simpan()
