"""Uji jembatan antara pipeline dan skrip evaluasi."""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.dialogue_state import INITIAL_PROFILE
from src.pipeline import TrainingPlanPipeline
from src.retriever import RetrievedDocument

COMPLETE_PROFILE = {
    "tujuan_latihan": "hipertrofi",
    "frekuensi_tersedia": 3,
    "level_pengalaman": "pemula",
    "riwayat_cedera": ["nyeri bahu kanan"],
    "catatan_tambahan": "",
}


def load_run_until_plan():
    source = (Path(__file__).resolve().parent.parent
              / "evaluation" / "run_eval.py").read_text(encoding="utf-8")
    start = source.index("def run_until_plan")
    end = source.index("async def run_scenario(")
    namespace: dict = {}
    exec(source[start:end], namespace)
    return namespace["run_until_plan"]


class FakeRetriever:
    def retrieve_full_documents(self, query, **kwargs):
        return [RetrievedDocument(
            source="acsm.pdf", full_text="Isi dokumen.", best_distance=None,
            num_chunks=1, num_hit_chunks=1, is_core=True,
            hit_chunks=["Isi dokumen."],
        )]


def build_pipeline(profiles):
    sequence = iter(profiles)
    calls = {"analyze": 0, "generate": 0}

    def analyze_fn(message, current_riwayat_cedera=None):
        calls["analyze"] += 1
        return next(sequence)

    def generate_fn(profile, context):
        calls["generate"] += 1
        return "Rencana latihan tiga sesi per minggu [S1]."

    pipeline = TrainingPlanPipeline(
        retriever=FakeRetriever(),
        analyze_fn=analyze_fn,
        generate_fn=generate_fn,
        compliance_fn=lambda plan, constraints: {"patuh": True, "pelanggaran": []},
        revise_fn=lambda *a: "tidak dipakai",
    )
    return pipeline, calls


def test_skenario_satu_giliran_tetap_sampai_ke_rencana():
    run_until_plan = load_run_until_plan()
    pipeline, calls = build_pipeline([COMPLETE_PROFILE])

    result = run_until_plan(pipeline, "hipertrofi, 3x seminggu, pemula, bahu nyeri")

    assert result.status == "rencana_siap", (
        f"status={result.status}. Tahap konfirmasi membuat evaluasi berhenti "
        f"sebelum rencana tersusun."
    )
    assert calls["generate"] == 1
    print("  ok  skenario satu giliran tetap sampai ke rencana meski ada konfirmasi")


def test_pembenaran_tidak_memanggil_analyzer():
    run_until_plan = load_run_until_plan()
    pipeline, calls = build_pipeline([COMPLETE_PROFILE])

    run_until_plan(pipeline, "hipertrofi, 3x seminggu, pemula, bahu nyeri")

    assert calls["analyze"] == 1, (
        f"analyzer dipanggil {calls['analyze']}x. Jawaban pembenaran seharusnya "
        f"ditangani tanpa memanggil model."
    )
    print("  ok  pemastian otomatis tidak memboroskan panggilan model")


def test_profil_belum_lengkap_tidak_dipaksa_lanjut():
    run_until_plan = load_run_until_plan()
    belum_lengkap = {**INITIAL_PROFILE, "tujuan_latihan": "hipertrofi"}
    pipeline, calls = build_pipeline([belum_lengkap, belum_lengkap, belum_lengkap])

    result = run_until_plan(pipeline, "mau nambah otot")

    assert result.status == "butuh_info"
    assert calls["generate"] == 0
    print("  ok  skenario yang memang belum lengkap tetap dilaporkan butuh_info")


def test_batas_giliran_mencegah_perulangan_tanpa_akhir():
    run_until_plan = load_run_until_plan()

    class StuckPipeline:
        def __init__(self):
            self.turns = 0

        def run(self, message):
            self.turns += 1

            class R:
                status = "butuh_konfirmasi"
            return R()

    pipeline = StuckPipeline()
    result = run_until_plan(pipeline, "apa saja", max_turns=3)

    assert pipeline.turns == 3, pipeline.turns
    assert result.status == "butuh_konfirmasi"
    print("  ok  batas giliran mencegah perulangan tanpa akhir")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"Menjalankan {len(tests)} tes alur evaluasi\n")
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  GAGAL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} tes lolos")
    sys.exit(1 if failed else 0)
