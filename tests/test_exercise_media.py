"""Uji pemeta ilustrasi gerakan (jalan tanpa API key maupun internet)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src import exercise_media
from src.exercise_media import (
    deteksi_gerakan,
    kumpulkan_media,
    normalisasi,
    ringkasan_katalog,
)

KATALOG_ASLI = Path(__file__).resolve().parent.parent / "data" / "gerakan" / "katalog_gerakan.json"


@pytest.fixture(autouse=True)
def _bersihkan_cache():
    exercise_media.bersihkan_cache()
    yield
    exercise_media.bersihkan_cache()


@pytest.fixture
def katalog_uji(tmp_path) -> str:
    """Katalog kecil buatan agar pengujian tidak bergantung pada isi katalog asli."""
    isi = {
        "versi": 1,
        "lisensi_media": "Unlicense (domain publik)",
        "sumber_media": "https://contoh.invalid/katalog",
        "gerakan": [
            {
                "id": "deadlift",
                "nama": "Deadlift",
                "nama_id": "Mengangkat barbel dari lantai",
                "pola_gerak": "dominan pinggul",
                "alias": ["barbell deadlift", "deadlift", "dead lift"],
                "kelompok_otot_utama": ["punggung bawah"],
                "kelompok_otot_pendukung": ["hamstring (paha belakang)"],
                "alat": "barbel",
                "langkah": ["Berdiri di depan barbel.", "Angkat dengan punggung lurus."],
                "poin_kunci": "Punggung wajib tetap lurus.",
                "gambar": [
                    {
                        "berkas": "uji_deadlift/0.jpg",
                        "asal": "https://contoh.invalid/deadlift/0.jpg",
                        "keterangan": "Posisi awal",
                    }
                ],
                "sumber_media": {"nama": "katalog uji", "lisensi": "Unlicense"},
            },
            {
                "id": "romanian_deadlift",
                "nama": "Romanian Deadlift",
                "nama_id": "Menurunkan barbel dengan pinggul mundur",
                "pola_gerak": "dominan pinggul",
                "alias": ["romanian deadlift", "rdl"],
                "kelompok_otot_utama": ["hamstring (paha belakang)"],
                "kelompok_otot_pendukung": [],
                "alat": "barbel",
                "langkah": ["Dorong pinggul ke belakang."],
                "poin_kunci": "Gerakan berasal dari pinggul.",
                "gambar": [],
                "sumber_media": {"nama": "katalog uji", "lisensi": "Unlicense"},
            },
            {
                "id": "push_up",
                "nama": "Push-up",
                "nama_id": "Mendorong badan dari lantai",
                "pola_gerak": "dorong horizontal",
                "alias": ["push up"],
                "kelompok_otot_utama": ["dada"],
                "kelompok_otot_pendukung": [],
                "alat": "berat badan sendiri",
                "langkah": ["Ambil posisi telungkup."],
                "poin_kunci": "Badan harus lurus.",
                "gambar": [],
                "sumber_media": {"nama": "katalog uji", "lisensi": "Unlicense"},
            },
        ],
    }
    berkas = tmp_path / "katalog_gerakan.json"
    berkas.write_text(json.dumps(isi, ensure_ascii=False), encoding="utf-8")
    return str(berkas)


# --------------------------------------------------------------- normalisasi

def test_normalisasi_menyamakan_tanda_hubung_dan_bentuk_rapat():
    assert normalisasi("Push-Up") == normalisasi("push up") == normalisasi("PUSHUP")


def test_normalisasi_membuang_penanda_sumber():
    assert "[s1]" not in normalisasi("Lakukan squat 3 set [S1].")


# ----------------------------------------------------------------- deteksi

def test_alias_terpanjang_menang(katalog_uji):
    hasil = deteksi_gerakan("Tambahkan romanian deadlift 3 set.", katalog_uji)
    assert hasil == [("romanian_deadlift", "romanian deadlift")]


def test_deadlift_biasa_tetap_terdeteksi(katalog_uji):
    hasil = deteksi_gerakan("Mulai dengan deadlift 4 set.", katalog_uji)
    assert hasil == [("deadlift", "deadlift")]


def test_urutan_mengikuti_kemunculan_pertama(katalog_uji):
    teks = "Hari 1 push-up, hari 2 deadlift, hari 3 push up lagi."
    assert [g for g, _ in deteksi_gerakan(teks, katalog_uji)] == ["push_up", "deadlift"]


def test_gerakan_tidak_diulang(katalog_uji):
    teks = "Deadlift dulu, lalu deadlift lagi, tutup dengan dead lift."
    assert len(deteksi_gerakan(teks, katalog_uji)) == 1


def test_penanda_sumber_tidak_mengganggu(katalog_uji):
    teks = "Lakukan deadlift 3 sampai 4 set [S1], lalu push-up sampai gagal [S2]."
    assert [g for g, _ in deteksi_gerakan(teks, katalog_uji)] == ["deadlift", "push_up"]


def test_tidak_cocok_di_tengah_kata(katalog_uji):
    assert deteksi_gerakan("Kata deadlifting seharusnya tidak dihitung.", katalog_uji) == []


def test_teks_kosong_aman(katalog_uji):
    assert deteksi_gerakan("", katalog_uji) == []
    assert kumpulkan_media("", path=katalog_uji) == []


def test_katalog_tidak_ada_tidak_menggagalkan(tmp_path):
    hilang = str(tmp_path / "tidak_ada.json")
    assert deteksi_gerakan("deadlift", hilang) == []
    assert kumpulkan_media("deadlift", path=hilang) == []


# ------------------------------------------------------------ kumpulkan media

def test_media_memuat_langkah_dan_gambar(katalog_uji):
    hasil = kumpulkan_media("Mulai dengan barbell deadlift.", path=katalog_uji)
    assert len(hasil) == 1

    gerakan = hasil[0]
    assert gerakan.id == "deadlift"
    assert gerakan.disebut_sebagai == "barbell deadlift"
    assert gerakan.langkah
    assert gerakan.poin_kunci
    # Berkas lokal belum diunduh pada lingkungan uji, jadi URL sumber dipakai.
    assert gerakan.gambar[0]["url"] == "https://contoh.invalid/deadlift/0.jpg"
    assert gerakan.gambar[0]["keterangan"] == "Posisi awal"


def test_gambar_lokal_diutamakan(katalog_uji, tmp_path, monkeypatch):
    lokal = tmp_path / "media"
    (lokal / "uji_deadlift").mkdir(parents=True)
    (lokal / "uji_deadlift" / "0.jpg").write_bytes(b"jpeg palsu")
    monkeypatch.setattr(exercise_media.config, "EXERCISE_MEDIA_DIR", str(lokal))

    gerakan = kumpulkan_media("deadlift", path=katalog_uji)[0]
    assert gerakan.gambar[0]["url"] == "/static/gerakan/uji_deadlift/0.jpg"


def test_batas_jumlah_dihormati(katalog_uji):
    teks = "deadlift, romanian deadlift, push up"
    assert len(kumpulkan_media(teks, batas=2, path=katalog_uji)) == 2


def test_to_dict_siap_dikirim_sebagai_json(katalog_uji):
    hasil = kumpulkan_media("deadlift", path=katalog_uji)[0].to_dict()
    json.dumps(hasil)  # tidak boleh melempar galat
    for kunci in ("id", "nama", "langkah", "gambar", "sumber_media", "disebut_sebagai"):
        assert kunci in hasil


# ------------------------------------------------------------- katalog nyata

@pytest.mark.skipif(not KATALOG_ASLI.exists(), reason="katalog belum dibangun")
class TestKatalogNyata:
    def test_setiap_entri_lengkap(self):
        katalog = json.loads(KATALOG_ASLI.read_text(encoding="utf-8"))
        assert katalog["gerakan"], "katalog kosong"
        for entri in katalog["gerakan"]:
            assert entri["alias"], entri["id"]
            assert len(entri["langkah"]) >= 3, entri["id"]
            assert entri["poin_kunci"], entri["id"]
            assert entri["gambar"], entri["id"]

    def test_tidak_ada_alias_dipakai_dua_gerakan(self):
        katalog = json.loads(KATALOG_ASLI.read_text(encoding="utf-8"))
        pemilik: dict[str, str] = {}
        for entri in katalog["gerakan"]:
            for alias in entri["alias"]:
                bentuk = normalisasi(alias)
                assert pemilik.get(bentuk, entri["id"]) == entri["id"], (
                    f"alias '{alias}' dipakai '{pemilik.get(bentuk)}' dan '{entri['id']}'"
                )
                pemilik[bentuk] = entri["id"]

    def test_setiap_gerakan_terdeteksi_dari_namanya_sendiri(self):
        katalog = json.loads(KATALOG_ASLI.read_text(encoding="utf-8"))
        for entri in katalog["gerakan"]:
            kalimat = f"Lakukan {entri['nama']} sebanyak 3 set [S1]."
            terdeteksi = [g for g, _ in deteksi_gerakan(kalimat)]
            assert entri["id"] in terdeteksi, entri["nama"]

    def test_ringkasan_katalog_konsisten(self):
        ringkasan = ringkasan_katalog()
        assert ringkasan["total_gerakan"] > 0
        assert ringkasan["total_gambar"] >= ringkasan["total_gerakan"]
        assert ringkasan["lisensi_media"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
