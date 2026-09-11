"""Uji lapis web secara luring dengan pipeline tiruan."""

from __future__ import annotations
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from web import app as web_app
from web.feedback import FeedbackStore
from web.session import SessionStore
from src.dialogue_state import INITIAL_PROFILE

COMPLETE_PROFILE = {
    "tujuan_latihan": "hipertrofi",
    "frekuensi_tersedia": 3,
    "level_pengalaman": "pemula",
    "riwayat_cedera": ["nyeri bahu kanan"],
    "catatan_tambahan": "",
}


class FakeDocument:
    def __init__(self, source, is_core, best_distance, num_chunks,
                 num_hit_chunks, hit_chunks):
        self.source = source
        self.is_core = is_core
        self.best_distance = best_distance
        self.num_chunks = num_chunks
        self.num_hit_chunks = num_hit_chunks
        self.hit_chunks = hit_chunks


class FakeResult:
    def __init__(self, status, message="", plan="", profile=None,
                 sources=None, compliance=None, warnings=None,
                 citations=None, documents=None, marked=0, total=0,
                 revisions=0, exercises=None):
        self.status = status
        self.message = message
        self.plan = plan
        self.extracted_profile = profile or dict(INITIAL_PROFILE)
        self.retrieved_sources = sources or []
        self.retrieved_documents = documents or []
        self.compliance = compliance or {}
        self.warnings = warnings or []
        self.citations = citations or []
        self.marked_sentences = marked
        self.total_sentences = total
        self.revision_attempts = revisions
        self.exercises = exercises or []


class FakePipeline:
    def __init__(self, script=None):
        self.profile = dict(INITIAL_PROFILE)
        self.calls = []
        self.script = list(script or [])

    def run(self, message):
        self.calls.append(message)
        if self.script:
            action = self.script.pop(0)
            if isinstance(action, Exception):
                raise action
            self.profile = action.extracted_profile
            return action
        return FakeResult("butuh_info", message="Boleh lengkapi dulu?")

    def reset(self):
        self.profile = dict(INITIAL_PROFILE)
        self.calls.append("__reset__")


def build_client(script_per_session=None):
    created = []

    def factory():
        pipeline = FakePipeline(script_per_session)
        created.append(pipeline)
        return pipeline

    web_app.state["ready"] = True
    web_app.state["error"] = None
    web_app.state["chunks"] = 589
    web_app.state["store"] = SessionStore(factory)
    web_app.state["feedback"] = FeedbackStore(
        Path(tempfile.mkdtemp()) / "feedback.jsonl"
    )
    return TestClient(web_app.app), created


def test_health_melaporkan_kesiapan():
    client, _ = build_client()
    data = client.get("/api/health").json()
    assert data["ready"] is True
    assert data["chunks"] == 589
    print("  ok  /api/health melaporkan kesiapan dan jumlah potongan")


def test_chat_membuat_session_id_baru():
    client, _ = build_client()
    data = client.post("/api/chat", json={"message": "halo"}).json()
    assert data["session_id"]
    assert data["status"] == "butuh_info"
    print("  ok  permintaan tanpa session_id menerima sesi baru")


def test_session_id_yang_sama_memakai_pipeline_yang_sama():
    client, created = build_client()
    first = client.post("/api/chat", json={"message": "satu"}).json()
    sid = first["session_id"]
    client.post("/api/chat", json={"message": "dua", "session_id": sid})
    assert len(created) == 1, f"{len(created)} pipeline dibuat, seharusnya 1"
    assert created[0].calls == ["satu", "dua"]
    print("  ok  session_id yang sama memakai pipeline yang sama")


def test_sesi_berbeda_terpisah_total():
    client, created = build_client()
    a = client.post("/api/chat", json={"message": "sesi A"}).json()
    b = client.post("/api/chat", json={"message": "sesi B"}).json()
    assert a["session_id"] != b["session_id"]
    assert len(created) == 2
    assert created[0].calls == ["sesi A"]
    assert created[1].calls == ["sesi B"]
    print("  ok  dua sesi berbeda tidak saling mencampuri riwayat")


def test_status_konfirmasi_mengirim_pesan_bukan_rencana():
    script = [FakeResult(
        "butuh_konfirmasi",
        message="Sudah benar semua?",
        profile=COMPLETE_PROFILE,
    )]
    client, _ = build_client(script)
    data = client.post("/api/chat", json={"message": "hipertrofi 3x pemula"}).json()
    assert data["status"] == "butuh_konfirmasi"
    assert data["message"] == "Sudah benar semua?"
    assert data["plan"] == ""
    print("  ok  status butuh_konfirmasi mengirim pesan konfirmasi, bukan rencana")


def test_rencana_siap_mengirim_plan_dan_sumber():
    script = [FakeResult(
        "rencana_siap",
        plan="Rencana latihan tiga sesi per minggu.",
        profile=COMPLETE_PROFILE,
        sources=["acsm.pdf", "ijerph-19-12710.pdf"],
        compliance={"patuh": True, "pelanggaran": []},
    )]
    client, _ = build_client(script)
    data = client.post("/api/chat", json={"message": "ya"}).json()
    assert data["status"] == "rencana_siap"
    assert data["plan"].startswith("Rencana latihan")
    assert data["sources"] == ["acsm.pdf", "ijerph-19-12710.pdf"]
    print("  ok  status rencana_siap mengirim rencana beserta daftar sumber")


def test_daftar_gerakan_dikirim_pada_rencana_siap():
    from src.exercise_media import ExerciseMedia

    gerakan = ExerciseMedia(
        id="deadlift",
        nama="Deadlift",
        nama_id="Mengangkat barbel dari lantai",
        pola_gerak="dominan pinggul",
        alat="barbel",
        kelompok_otot_utama=["punggung bawah"],
        kelompok_otot_pendukung=[],
        langkah=["Berdiri di depan barbel.", "Angkat dengan punggung lurus."],
        poin_kunci="Punggung wajib tetap lurus.",
        gambar=[{"url": "/static/gerakan/deadlift/0.jpg", "keterangan": "Posisi awal"}],
        sumber_media={"nama": "free-exercise-db", "lisensi": "Unlicense (domain publik)"},
        disebut_sebagai="deadlift",
    )
    script = [FakeResult(
        "rencana_siap",
        plan="Hari 1 deadlift 3 set [S1].",
        profile=COMPLETE_PROFILE,
        sources=["acsm.pdf"],
        exercises=[gerakan],
    )]
    client, _ = build_client(script)
    data = client.post("/api/chat", json={"message": "ya"}).json()

    assert len(data["exercises"]) == 1
    kartu = data["exercises"][0]
    assert kartu["nama"] == "Deadlift"
    assert kartu["langkah"]
    assert kartu["gambar"][0]["keterangan"] == "Posisi awal"
    assert kartu["sumber_media"]["lisensi"]
    print("  ok  rencana_siap mengirim ilustrasi gerakan beserta tata caranya")


def test_daftar_gerakan_kosong_saat_belum_ada_rencana():
    script = [FakeResult("butuh_info", message="Boleh lengkapi dulu?")]
    client, _ = build_client(script)
    data = client.post("/api/chat", json={"message": "halo"}).json()
    assert data["exercises"] == []
    print("  ok  status butuh_info tidak melampirkan ilustrasi gerakan")


def test_endpoint_katalog_gerakan_melaporkan_lisensi():
    client, _ = build_client()
    data = client.get("/api/katalog-gerakan").json()
    assert "total_gerakan" in data
    assert "lisensi_media" in data
    print("  ok  /api/katalog-gerakan melaporkan isi katalog dan lisensinya")


def test_profil_dikirim_sebagai_label_dan_nilai():
    script = [FakeResult("butuh_konfirmasi", message="cek", profile=COMPLETE_PROFILE)]
    client, _ = build_client(script)
    rows = client.post("/api/chat", json={"message": "apa saja"}).json()["profile"]
    labels = [r["label"] for r in rows]
    values = {r["label"]: r["value"] for r in rows}
    assert labels == ["Tujuan latihan", "Frekuensi per minggu",
                      "Level pengalaman", "Riwayat cedera"]
    assert values["Frekuensi per minggu"] == "3 hari per minggu"
    assert values["Riwayat cedera"] == "nyeri bahu kanan"
    print("  ok  profil dikirim sebagai pasangan label dan nilai yang siap tampil")


def test_galat_pipeline_menjaga_profil_dan_membalas_502():
    pipeline_holder = []

    def factory():
        p = FakePipeline([RuntimeError("503 UNAVAILABLE. high demand")])
        p.profile = dict(COMPLETE_PROFILE)
        pipeline_holder.append(p)
        return p

    web_app.state["ready"] = True
    web_app.state["error"] = None
    web_app.state["store"] = SessionStore(factory)
    client = TestClient(web_app.app)

    response = client.post("/api/chat", json={"message": "halo"})
    data = response.json()
    assert response.status_code == 502
    assert "503" in data["error"]
    assert data["filled_fields"] == 4
    assert data["session_id"]
    print("  ok  galat pipeline dibalas 502 dengan profil yang masih tersimpan")


def test_reset_mengosongkan_pipeline_sesi():
    client, created = build_client()
    sid = client.post("/api/chat", json={"message": "halo"}).json()["session_id"]
    data = client.post("/api/reset", json={"session_id": sid}).json()
    assert data["status"] == "reset"
    assert data["session_id"] == sid
    assert created[0].calls[-1] == "__reset__"
    print("  ok  /api/reset mengosongkan pipeline pada sesi yang sama")


def test_sistem_belum_siap_membalas_503():
    web_app.state["store"] = None
    web_app.state["error"] = "model gagal dimuat"
    client = TestClient(web_app.app)
    response = client.post("/api/chat", json={"message": "halo"})
    assert response.status_code == 503
    assert "model gagal dimuat" in response.json()["error"]
    print("  ok  permintaan saat sistem belum siap dibalas 503")


def test_pesan_kosong_ditolak():
    client, _ = build_client()
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    print("  ok  pesan kosong ditolak sebelum menyentuh pipeline")


def test_sesi_kedaluwarsa_dibersihkan():
    store = SessionStore(FakePipeline, ttl_seconds=0)
    first = store.get_or_create(None)
    second = store.get_or_create(first.session_id)
    assert second.session_id != first.session_id
    assert store.count() == 1
    print("  ok  sesi yang melewati batas waktu dibersihkan dari penyimpanan")


def test_jumlah_sesi_dibatasi():
    store = SessionStore(FakePipeline, max_sessions=3)
    for _ in range(6):
        store.get_or_create(None)
    assert store.count() <= 3, store.count()
    print("  ok  jumlah sesi tersimpan dibatasi agar memori tidak membengkak")


def test_halaman_utama_tersaji():
    client, _ = build_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "FitWise" in response.text
    print("  ok  halaman utama tersaji dari berkas statis")


def test_sitasi_dan_rasio_grounding_dikirim():
    script = [FakeResult(
        "rencana_siap",
        plan="Dua sesi per minggu sudah memadai [S1]. Hindari overhead press [S2].",
        profile=COMPLETE_PROFILE,
        sources=["acsm.pdf", "bahu.pdf"],
        citations=[
            {"marker": "S1", "number": 1, "source": "acsm.pdf", "valid": True},
            {"marker": "S2", "number": 2, "source": "bahu.pdf", "valid": True},
        ],
        marked=2, total=2,
    )]
    client, _ = build_client(script)
    data = client.post("/api/chat", json={"message": "ya"}).json()
    assert [c["marker"] for c in data["citations"]] == ["S1", "S2"]
    assert data["grounding"] == {"marked_sentences": 2, "total_sentences": 2}
    print("  ok  sitasi dan rasio grounding dikirim ke antarmuka")


def test_panel_transparansi_retrieval_dikirim():
    docs = [
        FakeDocument("acsm.pdf", True, None, 135, 8, ["Potongan inti pertama."]),
        FakeDocument("bahu.pdf", False, 0.4193, 78, 2,
                     ["Potongan bahu.", "Potongan bahu kedua."]),
    ]
    script = [FakeResult(
        "rencana_siap", plan="Rencana [S1].", profile=COMPLETE_PROFILE,
        sources=["acsm.pdf", "bahu.pdf"], documents=docs,
    )]
    client, _ = build_client(script)
    rows = client.post("/api/chat", json={"message": "ya"}).json()["retrieval"]
    assert [r["marker"] for r in rows] == ["S1", "S2"]
    assert rows[0]["is_core"] is True and rows[0]["best_distance"] is None
    assert rows[1]["best_distance"] == 0.4193
    assert rows[1]["num_hit_chunks"] == 2 and rows[1]["num_chunks"] == 78
    assert len(rows[1]["hit_previews"]) == 2
    print("  ok  panel transparansi memuat jarak, jumlah potongan, dan cuplikannya")


def test_jumlah_penyusunan_ulang_dilaporkan():
    script = [FakeResult(
        "rencana_siap", plan="Rencana revisi [S1].", profile=COMPLETE_PROFILE,
        sources=["acsm.pdf"], revisions=1,
        warnings=["Rencana disusun ulang 1 kali untuk memenuhi batasan riwayat cedera."],
    )]
    client, _ = build_client(script)
    data = client.post("/api/chat", json={"message": "ya"}).json()
    assert data["revision_attempts"] == 1
    assert any("disusun ulang" in w for w in data["warnings"])
    print("  ok  jumlah penyusunan ulang dilaporkan ke antarmuka")


def test_umpan_balik_tersimpan_dan_terbaca():
    client, _ = build_client()
    store = web_app.state["feedback"]
    sid = client.post("/api/chat", json={"message": "halo"}).json()["session_id"]

    response = client.post("/api/feedback", json={
        "session_id": sid, "rating": "berguna",
        "reason": "rencananya jelas dan ada sumbernya",
        "profile": {"Tujuan latihan": "hipertrofi"},
        "sources": ["acsm.pdf"], "plan_excerpt": "Rencana tiga sesi.",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "tersimpan"

    entries = store.read_all()
    assert len(entries) == 1
    assert entries[0]["rating"] == "berguna"
    assert entries[0]["alasan"] == "rencananya jelas dan ada sumbernya"
    assert entries[0]["sumber"] == ["acsm.pdf"]
    assert entries[0]["waktu"]
    print("  ok  umpan balik tersimpan lengkap dan dapat dibaca ulang")


def test_ringkasan_umpan_balik_menghitung_proporsi():
    client, _ = build_client()
    sid = client.post("/api/chat", json={"message": "halo"}).json()["session_id"]
    for rating in ["berguna", "berguna", "tidak_berguna"]:
        client.post("/api/feedback", json={"session_id": sid, "rating": rating})

    data = client.get("/api/feedback/summary").json()
    assert data["total"] == 3
    assert data["berguna"] == 2
    assert data["tidak_berguna"] == 1
    assert data["proporsi_berguna"] == 0.6667
    print("  ok  ringkasan umpan balik menghitung proporsi dengan benar")


def test_rating_tidak_dikenal_ditolak():
    client, _ = build_client()
    response = client.post("/api/feedback", json={
        "session_id": "abc", "rating": "bagus_banget",
    })
    assert response.status_code == 422
    assert web_app.state["feedback"].read_all() == []
    print("  ok  rating di luar pilihan ditolak sebelum tersimpan")


def test_alasan_terlalu_panjang_ditolak():
    client, _ = build_client()
    response = client.post("/api/feedback", json={
        "session_id": "abc", "rating": "berguna", "reason": "x" * 600,
    })
    assert response.status_code == 422
    print("  ok  alasan melebihi batas panjang ditolak")


def test_ringkasan_kosong_tidak_membagi_nol():
    client, _ = build_client()
    data = client.get("/api/feedback/summary").json()
    assert data == {"total": 0, "berguna": 0, "tidak_berguna": 0,
                    "proporsi_berguna": None}
    print("  ok  ringkasan tanpa data tidak melakukan pembagian dengan nol")


def test_jawaban_lanjutan_dikirim_dengan_sitasi():
    docs = [FakeDocument("acsm.pdf", True, None, 135, 8, ["Potongan inti."])]
    script = [FakeResult(
        "jawaban_lanjutan",
        message="Gerakan itu dihindari karena rotasi ekstrem [S1].",
        profile=COMPLETE_PROFILE, sources=["acsm.pdf"], documents=docs,
        citations=[{"marker": "S1", "number": 1, "source": "acsm.pdf",
                    "valid": True}],
        marked=1, total=1,
    )]
    client, _ = build_client(script)
    data = client.post("/api/chat", json={"message": "kenapa?"}).json()

    assert data["status"] == "jawaban_lanjutan"
    assert data["has_plan"] is True
    assert data["plan"] == "", "jawaban lanjutan tidak boleh mengisi medan plan"
    assert data["citations"][0]["source"] == "acsm.pdf"
    assert len(data["retrieval"]) == 1
    print("  ok  jawaban lanjutan dikirim beserta sitasi dan panel retrieval")


def test_status_tanpa_rencana_menandai_has_plan_salah():
    script = [FakeResult("butuh_info", message="Boleh lengkapi dulu?")]
    client, _ = build_client(script)
    data = client.post("/api/chat", json={"message": "halo"}).json()
    assert data["has_plan"] is False
    print("  ok  status sebelum rencana menandai has_plan bernilai salah")


class FakeRetrieverKB:
    def describe_documents(self):
        return [
            {"source": "american_college_of_sports_medicine_position.21.pdf",
             "is_core": True, "num_chunks": 135, "characters": 94588},
            {"source": "ijerph-19-12710.pdf",
             "is_core": False, "num_chunks": 152, "characters": 103371},
            {"source": "berkas_tak_dikenal.pdf",
             "is_core": False, "num_chunks": 10, "characters": 5000},
        ]


def test_ringkasan_basis_pengetahuan_dikirim():
    client, _ = build_client()
    web_app.state["retriever"] = FakeRetrieverKB()
    data = client.get("/api/knowledge-base").json()

    assert data["total_documents"] == 3
    assert data["total_chunks"] == 297
    assert data["total_characters"] == 202959
    kat = {d["source"]: d["kategori"] for d in data["documents"]}
    assert kat["ijerph-19-12710.pdf"] == "Cedera umum di pusat kebugaran"
    assert kat["berkas_tak_dikenal.pdf"] == "Dokumen pendukung"
    assert data["documents"][0]["is_core"] is True, "dokumen inti harus di urutan awal"
    print("  ok  ringkasan basis pengetahuan memuat kategori dan total yang benar")


def test_basis_pengetahuan_saat_belum_siap():
    web_app.state["ready"] = False
    client = TestClient(web_app.app)
    assert client.get("/api/knowledge-base").status_code == 503
    web_app.state["ready"] = True
    print("  ok  permintaan basis pengetahuan saat belum siap dibalas 503")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"Menjalankan {len(tests)} tes lapis web (luring, tanpa API key)\n")
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  GAGAL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} tes lolos")
    sys.exit(1 if failed else 0)
