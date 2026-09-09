"""Uji penanda sumber pada rencana latihan."""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.citations import (
    build_citation_map,
    count_sentences_with_marker,
    strip_source_markers,
    used_marker_numbers,
)

PLAN = (
    "Buat kamu yang masih pemula, dua sesi per minggu sudah memadai untuk "
    "memicu hipertrofi [S1]. Hindari dulu gerakan menekan beban di atas kepala "
    "sampai keluhan bahumu mereda [S2]. Semangat ya."
)


def test_penanda_terbaca_dan_diurutkan():
    assert used_marker_numbers(PLAN) == [1, 2]
    assert used_marker_numbers("tanpa penanda") == []
    assert used_marker_numbers("[S2] lalu [S1] lalu [S2]") == [1, 2]
    print("  ok  penanda terbaca, diurutkan, dan tidak diulang")


def test_penanda_dibuang_tanpa_menyisakan_spasi_ganjil():
    hasil = strip_source_markers(PLAN)
    assert "[S1]" not in hasil and "[S2]" not in hasil
    assert "hipertrofi." in hasil, hasil
    assert "  " not in hasil
    assert " ." not in hasil
    print("  ok  penanda dibuang tanpa menyisakan spasi atau titik menggantung")


def test_pemetaan_penanda_ke_nama_berkas():
    sumber = ["acsm.pdf", "ijerph-19-12710.pdf"]
    peta = build_citation_map(PLAN, sumber)
    assert [c["marker"] for c in peta] == ["S1", "S2"]
    assert peta[0]["source"] == "acsm.pdf"
    assert peta[1]["source"] == "ijerph-19-12710.pdf"
    assert all(c["valid"] for c in peta)
    print("  ok  penanda dipetakan ke nama berkas sumber yang benar")


def test_penanda_di_luar_jangkauan_ditandai_tidak_sah():
    peta = build_citation_map("Klaim mengada-ada [S7].", ["acsm.pdf"])
    assert peta[0]["valid"] is False
    assert peta[0]["source"] is None
    print("  ok  penanda yang menunjuk sumber tidak ada ditandai tidak sah")


def test_rasio_kalimat_bertanda():
    marked, total = count_sentences_with_marker(PLAN)
    assert total == 2, f"kalimat pendek seperti sapaan seharusnya diabaikan, total={total}"
    assert marked == 2
    print("  ok  rasio kalimat bertanda mengabaikan sapaan pendek")


def test_teks_kosong_tidak_menjatuhkan_program():
    assert strip_source_markers("") == ""
    assert used_marker_numbers("") == []
    assert build_citation_map("", ["a.pdf"]) == []
    assert count_sentences_with_marker("") == (0, 0)
    print("  ok  teks kosong ditangani tanpa galat")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"Menjalankan {len(tests)} tes penanda sumber\n")
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  GAGAL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} tes lolos")
    sys.exit(1 if failed else 0)
