"""
Unit test untuk dialogue_state.py. Jalankan dengan:
    python3 -m pytest tests/test_dialogue_state.py -v
atau langsung:
    python3 tests/test_dialogue_state.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.dialogue_state import (
    INITIAL_PROFILE,
    REQUIRED_FIELDS,
    merge_profile,
    get_missing_fields,
    build_clarifying_question,
)


def test_fresh_profile_missing_semuanya():
    missing = get_missing_fields(INITIAL_PROFILE)
    assert missing == REQUIRED_FIELDS, "Profil kosong harus kurang di semua field wajib"
    print("  ok  Profil kosong -> semua field wajib terdeteksi kurang")


def test_merge_tidak_menimpa_field_yang_udah_kejawab():
    profile = merge_profile(INITIAL_PROFILE, {
        "tujuan_latihan": "hipertrofi",
        "frekuensi_tersedia": 5,
        "level_pengalaman": None,
        "riwayat_cedera": None,
        "catatan_tambahan": "",
    })
    profile = merge_profile(profile, {
        "tujuan_latihan": None,
        "frekuensi_tersedia": None,
        "level_pengalaman": "menengah",
        "riwayat_cedera": None,
        "catatan_tambahan": "",
    })
    assert profile["tujuan_latihan"] == "hipertrofi"
    assert profile["frekuensi_tersedia"] == 5
    assert profile["level_pengalaman"] == "menengah"
    print("  ok  merge_profile mengakumulasi data antar pesan, nggak saling menimpa")


def test_riwayat_cedera_tri_state():
    profile = merge_profile(INITIAL_PROFILE, {"riwayat_cedera": None})
    assert get_missing_fields(profile) and "riwayat_cedera" in get_missing_fields(profile)

    profile = merge_profile(INITIAL_PROFILE, {"riwayat_cedera": []})
    assert "riwayat_cedera" not in get_missing_fields(profile)
    assert profile["riwayat_cedera"] == []

    profile = merge_profile(INITIAL_PROFILE, {"riwayat_cedera": ["cedera lutut"]})
    assert profile["riwayat_cedera"] == ["cedera lutut"]
    print("  ok  riwayat_cedera membedakan 'belum dijawab' vs 'eksplisit nggak ada'")


def test_get_missing_fields_hanya_yang_kurang():
    profile = {
        "tujuan_latihan": "hipertrofi",
        "frekuensi_tersedia": 5,
        "level_pengalaman": "tidak_disebutkan",
        "riwayat_cedera": [],
        "catatan_tambahan": "",
    }
    missing = get_missing_fields(profile)
    assert missing == ["level_pengalaman"], f"Harusnya cuma level_pengalaman yang kurang, dapat: {missing}"
    print("  ok  get_missing_fields cuma nunjukin field yang beneran masih kurang")


def test_profil_lengkap_tidak_ada_yang_kurang():
    profile = {
        "tujuan_latihan": "hipertrofi",
        "frekuensi_tersedia": 5,
        "level_pengalaman": "menengah",
        "riwayat_cedera": [],
        "catatan_tambahan": "",
    }
    assert get_missing_fields(profile) == []
    print("  ok  Profil lengkap -> nggak ada field yang kurang")


def test_clarifying_question_cuma_nanya_yang_kurang():
    profile = {
        "tujuan_latihan": "hipertrofi",
        "frekuensi_tersedia": 5,
        "level_pengalaman": None,
        "riwayat_cedera": None,
        "catatan_tambahan": "",
    }
    missing = get_missing_fields(profile)
    question = build_clarifying_question(profile, missing)

    assert "level" in question.lower(), "Pertanyaan harus nyinggung level pengalaman"
    assert "cedera" in question.lower(), "Pertanyaan harus nyinggung riwayat cedera"
    assert "tujuan latihannya apa" not in question.lower()
    assert "berapa hari" not in question.lower()
    print("  ok  Pertanyaan lanjutan cuma nanya field yang masih kurang")


def test_clarifying_question_single_missing_field():
    profile = {
        "tujuan_latihan": "hipertrofi",
        "frekuensi_tersedia": 5,
        "level_pengalaman": "menengah",
        "riwayat_cedera": None,
        "catatan_tambahan": "",
    }
    question = build_clarifying_question(profile, ["riwayat_cedera"])
    assert "cedera" in question.lower()
    print("  ok  Pertanyaan untuk 1 field yang kurang tetap natural (bukan bullet list)")


if __name__ == "__main__":
    tests = [
        test_fresh_profile_missing_semuanya,
        test_merge_tidak_menimpa_field_yang_udah_kejawab,
        test_riwayat_cedera_tri_state,
        test_get_missing_fields_hanya_yang_kurang,
        test_profil_lengkap_tidak_ada_yang_kurang,
        test_clarifying_question_cuma_nanya_yang_kurang,
        test_clarifying_question_single_missing_field,
    ]
    print(f"Menjalankan {len(tests)} test...\n")
    for t in tests:
        t()
    print("\nSemua test lolos!")
