"""Uji orkestrasi pipeline secara luring, tanpa memanggil Gemini dan tanpa GEMINI_API_KEY."""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline import TrainingPlanPipeline
from src.retriever import RetrievedDocument, collect_evaluation_contexts
from src.dialogue_state import (
    build_profile_summary,
    is_affirmative,
    is_negative,
)


class FakeRetriever:
    """Pengganti Retriever yang mengembalikan dokumen tetap."""

    def __init__(self, documents=None):
        self.documents = documents if documents is not None else [
            RetrievedDocument(
                source="acsm_sports_medicine_position.pdf",
                full_text="Prinsip A.\n\nPrinsip B.\n\nPrinsip C.",
                best_distance=None,
                num_chunks=3,
                num_hit_chunks=2,
                is_core=True,
                hit_chunks=["Prinsip A.", "Prinsip B."],
            ),
            RetrievedDocument(
                source="cedera_bahu.pdf",
                full_text="Hindari gerakan X.\n\nGunakan gerakan Y.",
                best_distance=0.4193,
                num_chunks=2,
                num_hit_chunks=1,
                is_core=False,
                hit_chunks=["Hindari gerakan X."],
            ),
        ]
        self.last_query = None

    def retrieve_full_documents(self, query, **kwargs):
        self.last_query = query
        return self.documents


def fake_analyzer(results_per_turn):
    sequence = iter(results_per_turn)

    def _fn(user_message, current_riwayat_cedera=None):
        return next(sequence)

    return _fn


def build_pipeline(analyzer_results, *, compliant=True, retriever=None,
                   compliance_sequence=None):
    calls = {"generate": 0, "compliance": 0, "revise": 0, "followup": 0}
    verdicts = iter(compliance_sequence or [])

    def generate_fn(profile, context):
        calls["generate"] += 1
        return f"RENCANA #{calls['generate']} untuk {profile['tujuan_latihan']} [S1]"

    def revise_fn(profile, context, previous_plan, violations):
        calls["revise"] += 1
        return f"RENCANA REVISI #{calls['revise']} [S1]"

    def followup_fn(profile, context, plan, question):
        calls["followup"] += 1
        return f"JAWABAN LANJUTAN untuk: {question} [S1]"

    def compliance_fn(plan, constraints):
        calls["compliance"] += 1
        if compliance_sequence:
            patuh = next(verdicts, True)
            return {"patuh": patuh, "pelanggaran": [] if patuh else ["gerakan X"]}
        return {"patuh": compliant, "pelanggaran": [] if compliant else ["gerakan X"]}

    p = TrainingPlanPipeline(
        retriever=retriever or FakeRetriever(),
        analyze_fn=fake_analyzer(analyzer_results),
        generate_fn=generate_fn,
        compliance_fn=compliance_fn,
        revise_fn=revise_fn,
        followup_fn=followup_fn,
    )
    return p, calls


COMPLETE_PROFILE = {
    "tujuan_latihan": "hipertrofi",
    "frekuensi_tersedia": 3,
    "level_pengalaman": "pemula",
    "riwayat_cedera": ["nyeri bahu"],
    "catatan_tambahan": "",
}


def test_profil_belum_lengkap_memicu_pertanyaan():
    p, calls = build_pipeline([
        {"tujuan_latihan": "hipertrofi", "frekuensi_tersedia": None,
         "level_pengalaman": None, "riwayat_cedera": None, "catatan_tambahan": ""},
    ])
    hasil = p.run("mau nambah otot dong")
    assert hasil.status == "butuh_info", hasil.status
    assert hasil.message
    assert calls["generate"] == 0, "generator tidak boleh dipanggil sebelum lengkap"
    print("  ok  profil belum lengkap -> butuh_info, generator tidak dipanggil")


def test_profil_lengkap_menghasilkan_rencana():
    p, calls = build_pipeline([COMPLETE_PROFILE])
    p.run("hipertrofi, 3x seminggu, pemula, bahu kanan nyeri")
    hasil = confirm(p)
    assert hasil.status == "rencana_siap", hasil.status
    assert hasil.plan.startswith("RENCANA #1")
    assert len(hasil.retrieved_sources) == 2
    assert calls["generate"] == 1 and calls["compliance"] == 1
    print("  ok  profil lengkap -> rencana_siap, retrieval dan compliance jalan")


def test_kueri_retrieval_memuat_seluruh_aspek():
    r = FakeRetriever()
    p, _ = build_pipeline([COMPLETE_PROFILE], retriever=r)
    p.run("apa saja")
    confirm(p)
    q = r.last_query
    assert "hipertrofi" in q and "nyeri bahu" in q and "pemula" in q, q
    print(f"  ok  kueri retrieval memuat tujuan, cedera, dan level: {q!r}")


def test_pertanyaan_lanjutan_dijawab_tanpa_menyusun_ulang():
    p, calls = build_pipeline([
        COMPLETE_PROFILE,
        {"tujuan_latihan": None, "frekuensi_tersedia": None,
         "level_pengalaman": None, "riwayat_cedera": None, "catatan_tambahan": ""},
    ])
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    confirm(p)
    hasil = p.run("kenapa gerakan menekan di atas kepala dihindari?")

    assert hasil.status == "jawaban_lanjutan", hasil.status
    assert "kenapa gerakan menekan" in hasil.message
    assert calls["followup"] == 1
    assert calls["generate"] == 1, (
        f"rencana disusun ulang {calls['generate']}x, pertanyaan lanjutan "
        f"seharusnya tidak memicu penyusunan ulang"
    )
    print("  ok  pertanyaan lanjutan dijawab tanpa menyusun ulang rencana")


def test_jawaban_lanjutan_memakai_konteks_yang_sama():
    catatan = {}

    def followup_fn(profile, context, plan, question):
        catatan["context"] = context
        catatan["plan"] = plan
        return "jawaban [S1]"

    p, _ = build_pipeline([
        COMPLETE_PROFILE,
        {"tujuan_latihan": None, "frekuensi_tersedia": None,
         "level_pengalaman": None, "riwayat_cedera": None, "catatan_tambahan": ""},
    ])
    p._followup = followup_fn
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    confirm(p)
    hasil = p.run("boleh tanya soal set-nya?")

    assert catatan["context"], "konteks tidak diteruskan ke jawaban lanjutan"
    assert catatan["plan"].startswith("RENCANA"), catatan["plan"]
    assert hasil.retrieved_sources, "sumber tidak ikut dikembalikan"
    assert hasil.citations, "penanda sumber tidak dipetakan"
    print("  ok  jawaban lanjutan memakai konteks dan rencana yang tersimpan")


def test_reset_mengosongkan_konteks_tersimpan():
    p, _ = build_pipeline([COMPLETE_PROFILE])
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    confirm(p)
    assert p.last_context and p.last_plan and p.last_documents
    p.reset()
    assert p.last_context == "" and p.last_plan == "" and p.last_documents == []
    print("  ok  reset mengosongkan konteks dan rencana yang tersimpan")


def test_perubahan_profil_meregenerasi_rencana():
    updated_profile = dict(COMPLETE_PROFILE, frekuensi_tersedia=5)
    p, calls = build_pipeline([COMPLETE_PROFILE, updated_profile])
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    confirm(p)
    p.run("eh, ternyata bisa 5x seminggu")
    hasil = confirm(p)
    assert hasil.status == "rencana_siap", hasil.status
    assert calls["generate"] == 2
    print("  ok  perubahan profil memicu penyusunan ulang rencana")


def test_pelanggaran_compliance_masuk_warnings():
    p, _ = build_pipeline([COMPLETE_PROFILE], compliant=False)
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    hasil = confirm(p)
    assert hasil.compliance["patuh"] is False
    assert any("melanggar" in w for w in hasil.warnings), hasil.warnings
    print("  ok  pelanggaran constraint tercatat di warnings")


def test_reset_mengosongkan_state():
    p, calls = build_pipeline([COMPLETE_PROFILE, COMPLETE_PROFILE])
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    confirm(p)
    p.reset()
    assert p.plan_ready is False
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    hasil = confirm(p)
    assert hasil.status == "rencana_siap"
    assert calls["generate"] == 2
    print("  ok  reset mengosongkan profil dan penanda rencana")


def test_konteks_evaluasi_mode_potongan_lebih_ringkas():
    docs = FakeRetriever().documents
    full = collect_evaluation_contexts(docs, mode="full_document")
    chunks = collect_evaluation_contexts(docs, mode="retrieved_chunks")
    assert len(full) == 2
    assert len(chunks) == 3, potongan
    assert all(d.source in "".join(chunks) for d in docs)
    assert sum(len(c) for c in chunks) < sum(len(c) for c in full) + 200
    print(f"  ok  mode potongan menghasilkan {len(chunks)} item konteks "
          f"(mode dokumen penuh: {len(full)})")


def test_dokumen_inti_tanpa_hit_tetap_masuk_konteks():
    docs = [RetrievedDocument(
        source="inti.pdf",
        full_text="Bagian satu.\n\nBagian dua.",
        best_distance=None,
        num_chunks=2,
        num_hit_chunks=0,
        is_core=True,
        hit_chunks=[],
    )]
    chunks = collect_evaluation_contexts(docs, mode="retrieved_chunks")
    assert len(chunks) == 2, potongan
    print("  ok  dokumen inti tanpa potongan terambil tetap terwakili di konteks")


def confirm(pipeline):
    return pipeline.run("ya")


def test_profil_lengkap_minta_konfirmasi_dulu():
    p, calls = build_pipeline([COMPLETE_PROFILE])
    hasil = p.run("hipertrofi, 3x seminggu, pemula, bahu kanan nyeri")
    assert hasil.status == "butuh_konfirmasi", hasil.status
    assert calls["generate"] == 0, "rencana tidak boleh disusun sebelum dikonfirmasi"
    for potongan in ["hipertrofi", "3 hari per minggu", "pemula", "nyeri bahu"]:
        assert potongan in hasil.message, f"{potongan!r} tidak muncul di ringkasan"
    print("  ok  profil lengkap -> minta konfirmasi, generator belum dipanggil")


def test_konfirmasi_ya_menyusun_rencana():
    p, calls = build_pipeline([COMPLETE_PROFILE])
    p.run("hipertrofi, 3x seminggu, pemula, bahu kanan nyeri")
    hasil = confirm(p)
    assert hasil.status == "rencana_siap", hasil.status
    assert calls["generate"] == 1
    print("  ok  jawaban 'ya' menyusun rencana")


def test_konfirmasi_ya_tidak_memanggil_analyzer():
    calls = {"analyze": 0}
    profil_iter = iter([COMPLETE_PROFILE])

    def analyze(user_message, current_riwayat_cedera=None):
        calls["analyze"] += 1
        return next(profil_iter)

    p = TrainingPlanPipeline(
        retriever=FakeRetriever(),
        analyze_fn=analyze,
        generate_fn=lambda profile, context: "RENCANA",
        compliance_fn=lambda plan, constraints: {"patuh": True, "pelanggaran": []},
    )
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    p.run("ya")
    assert calls["analyze"] == 1, (
        f"analyzer dipanggil {calls['analyze']}x, jawaban 'ya' tidak perlu dianalisis"
    )
    print("  ok  jawaban 'ya' tidak memboroskan panggilan analyzer")


def test_koreksi_saat_konfirmasi_menampilkan_ringkasan_baru():
    updated_profile = dict(COMPLETE_PROFILE, frekuensi_tersedia=5)
    p, calls = build_pipeline([COMPLETE_PROFILE, updated_profile])
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    hasil = p.run("eh salah, 5 hari seminggu")
    assert hasil.status == "butuh_konfirmasi", hasil.status
    assert "5 hari per minggu" in hasil.message
    assert calls["generate"] == 0, "koreksi tidak boleh langsung menyusun rencana"
    print("  ok  koreksi saat konfirmasi menampilkan ringkasan yang sudah diperbarui")


def test_penolakan_saat_konfirmasi_menanyakan_bagian_yang_salah():
    p, calls = build_pipeline([COMPLETE_PROFILE, COMPLETE_PROFILE])
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    hasil = p.run("belum")
    assert hasil.status == "butuh_konfirmasi", hasil.status
    assert "bagian mana" in hasil.message.lower()
    assert calls["generate"] == 0
    print("  ok  penolakan saat konfirmasi menanyakan bagian yang perlu diperbaiki")


def test_perubahan_profil_setelah_rencana_minta_konfirmasi_ulang():
    updated_profile = dict(COMPLETE_PROFILE, frekuensi_tersedia=5)
    p, calls = build_pipeline([COMPLETE_PROFILE, updated_profile])
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    confirm(p)
    hasil = p.run("ternyata bisa 5x seminggu")
    assert hasil.status == "butuh_konfirmasi", hasil.status
    assert calls["generate"] == 1, "rencana baru harus menunggu konfirmasi"
    print("  ok  perubahan profil setelah rencana jadi tetap minta konfirmasi ulang")


def test_penanda_konfirmasi_ikut_direset():
    p, _ = build_pipeline([COMPLETE_PROFILE])
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    assert p.awaiting_confirmation is True
    p.reset()
    assert p.awaiting_confirmation is False
    print("  ok  reset mengosongkan penanda menunggu konfirmasi")


def test_deteksi_jawaban_ya_dan_tidak():
    for kalimat in ["ya", "iya", "sudah benar", "oke lanjut", "betul semua", "sip"]:
        assert is_affirmative(kalimat), kalimat
    for kalimat in ["belum", "salah", "nggak", "ada yang keliru"]:
        assert is_negative(kalimat), kalimat
        assert not is_affirmative(kalimat), kalimat
    for kalimat in ["frekuensinya 4 hari", "levelku menengah", "cedera lutut kiri"]:
        assert not is_affirmative(kalimat), kalimat
    print("  ok  deteksi jawaban ya dan tidak membedakan koreksi dari pembenaran")


def test_ringkasan_menampilkan_seluruh_field():
    ringkasan = build_profile_summary(COMPLETE_PROFILE)
    for label in ["Tujuan latihan", "Frekuensi per minggu", "Level pengalaman",
                  "Riwayat cedera"]:
        assert label in ringkasan, label
    kosong = build_profile_summary(
        dict(COMPLETE_PROFILE, riwayat_cedera=[])
    )
    assert "tidak ada" in kosong
    print("  ok  ringkasan memuat keempat field, termasuk cedera kosong")


def test_pelanggaran_memicu_penyusunan_ulang():
    p, calls = build_pipeline([COMPLETE_PROFILE], compliance_sequence=[False, True])
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    hasil = confirm(p)
    assert hasil.status == "rencana_siap"
    assert calls["revise"] == 1, f"revisi dipanggil {calls['revise']}x, seharusnya 1"
    assert hasil.plan.startswith("RENCANA REVISI"), hasil.plan
    assert hasil.compliance["patuh"] is True
    assert hasil.revision_attempts == 1
    print("  ok  pelanggaran memicu penyusunan ulang, rencana akhir yang patuh dipakai")


def test_penyusunan_ulang_dibatasi_dan_peringatan_muncul():
    p, calls = build_pipeline([COMPLETE_PROFILE], compliant=False)
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    hasil = confirm(p)
    assert calls["revise"] == 2, f"revisi dipanggil {calls['revise']}x, batasnya 2"
    assert hasil.revision_attempts == 2
    assert any("masih melanggar" in w for w in hasil.warnings), hasil.warnings
    print("  ok  penyusunan ulang berhenti pada batas dan memunculkan peringatan")


def test_rencana_patuh_tidak_memicu_revisi():
    p, calls = build_pipeline([COMPLETE_PROFILE])
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    hasil = confirm(p)
    assert calls["revise"] == 0
    assert hasil.revision_attempts == 0
    assert hasil.warnings == []
    print("  ok  rencana yang sudah patuh tidak disusun ulang")


def test_hasil_memuat_pemetaan_sitasi():
    p, _ = build_pipeline([COMPLETE_PROFILE])
    p.run("hipertrofi, 3x seminggu, pemula, bahu nyeri")
    hasil = confirm(p)
    assert hasil.citations, "sitasi tidak terisi"
    assert hasil.citations[0]["marker"] == "S1"
    assert hasil.citations[0]["source"] == "acsm_sports_medicine_position.pdf"
    print("  ok  hasil memuat pemetaan penanda sumber ke nama berkas")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"Menjalankan {len(tests)} tes pipeline (luring, tanpa API key)\n")
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  GAGAL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} tes lolos")
    sys.exit(1 if failed else 0)
