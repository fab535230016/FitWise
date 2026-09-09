"""Uji logika pencocokan pada evaluasi Dialogue Analyzer."""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.dialogue_cases import DIALOGUE_CASES
from evaluation.run_dialogue_eval import (
    cocok_cedera,
    cocok_kategori,
    cocok_slot,
    inti_cedera,
)
from src.dialogue_state import REQUIRED_FIELDS


def test_sinonim_tujuan_dianggap_cocok():
    assert cocok_kategori("tujuan_latihan", "hipertrofi", "Hypertrophy")
    assert cocok_kategori("tujuan_latihan", "kekuatan", "kekuatan maksimal")
    assert cocok_kategori("tujuan_latihan", "penurunan berat badan", "fat loss")
    assert not cocok_kategori("tujuan_latihan", "hipertrofi", "kekuatan")
    print("  ok  sinonim tujuan latihan dikenali, yang berbeda tetap ditolak")


def test_sinonim_level_dianggap_cocok():
    assert cocok_kategori("level_pengalaman", "pemula", "Beginner")
    assert cocok_kategori("level_pengalaman", "lanjutan", "mahir")
    assert not cocok_kategori("level_pengalaman", "pemula", "menengah")
    print("  ok  sinonim level pengalaman dikenali")


def test_frekuensi_dibandingkan_sebagai_angka():
    assert cocok_slot("frekuensi_tersedia", 3, 3)
    assert cocok_slot("frekuensi_tersedia", 3, "3")
    assert not cocok_slot("frekuensi_tersedia", 3, 4)
    print("  ok  frekuensi dibandingkan sebagai angka, bukan teks")


def test_tiga_keadaan_cedera_dibedakan():
    assert cocok_cedera(None, None)
    assert cocok_cedera([], [])
    assert not cocok_cedera(None, []), "belum dijawab tidak sama dengan tidak ada"
    assert not cocok_cedera([], None)
    assert not cocok_cedera([], ["nyeri bahu"])
    print("  ok  tiga keadaan riwayat cedera dibedakan dengan tegas")


def test_cedera_cocok_lewat_kata_inti():
    assert cocok_cedera(["nyeri bahu kanan"], ["bahu kanan bermasalah"])
    assert cocok_cedera(["nyeri lutut"], ["keluhan pada lutut"])
    assert not cocok_cedera(["nyeri bahu kanan"], ["nyeri bahu kiri"])
    assert not cocok_cedera(["nyeri lutut"], ["nyeri bahu"])
    print("  ok  cedera dicocokkan lewat kata inti, sisi tubuh tetap dibedakan")


def test_jumlah_cedera_harus_sama():
    assert not cocok_cedera(["nyeri bahu"], ["nyeri bahu", "nyeri lutut"])
    assert cocok_cedera(["nyeri bahu", "cedera pergelangan kaki"],
                        ["pergelangan kaki keseleo", "bahu nyeri"])
    print("  ok  jumlah cedera harus sama, urutannya boleh berbeda")


def test_kata_umum_diabaikan_saat_mencocokkan():
    assert inti_cedera("nyeri bahu kanan") == {"bahu", "kanan"}
    assert "cedera" not in inti_cedera("cedera lutut kiri")
    print("  ok  kata umum seperti nyeri dan cedera diabaikan")


def test_slot_kosong_dan_tidak_disebutkan_setara():
    assert cocok_slot("level_pengalaman", None, None)
    assert cocok_slot("level_pengalaman", None, "tidak_disebutkan")
    assert not cocok_slot("level_pengalaman", None, "pemula")
    print("  ok  slot kosong setara dengan nilai tidak_disebutkan")


def test_setiap_kasus_punya_label_lengkap():
    for kasus in DIALOGUE_CASES:
        assert kasus["id"] and kasus["keterangan"], kasus
        assert kasus["turns"], kasus["id"]
        for t in kasus["turns"]:
            assert t["message"].strip(), kasus["id"]
            asing = set(t["expected"]) - set(REQUIRED_FIELDS)
            assert not asing, f"{kasus['id']}: slot tidak dikenal {asing}"
    print(f"  ok  {len(DIALOGUE_CASES)} kasus punya label yang lengkap dan sah")


def test_kasus_mencakup_perilaku_sulit():
    gabungan = " ".join(
        (k["id"] + " " + k["keterangan"]).lower() for k in DIALOGUE_CASES
    )
    for perilaku in ["koreksi", "eksplisit", "singkat", "bertahap", "bertambah"]:
        assert perilaku in gabungan, f"tidak ada kasus yang menguji {perilaku}"
    print("  ok  dataset mencakup koreksi, penolakan eksplisit, jawaban singkat, "
          "dan cedera bertambah")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"Menjalankan {len(tests)} tes pencocokan evaluasi dialog\n")
    gagal = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            gagal += 1
            print(f"  GAGAL  {t.__name__}: {e}")
    print(f"\n{len(tests) - gagal}/{len(tests)} tes lolos")
    sys.exit(1 if gagal else 0)
