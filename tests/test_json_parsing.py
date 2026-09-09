"""
Unit test untuk helper parsing JSON toleran di generator.py (_parse_json_response).
Nggak butuh GEMINI_API_KEY/internet karena cuma nes-test fungsi parsing-nya,
bukan manggil API beneran. Jalankan dengan:
    python3 -m pytest tests/test_json_parsing.py -v
atau langsung:
    python3 tests/test_json_parsing.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generator import _parse_json_response


def test_json_valid_langsung_parse():
    raw = '{"tujuan_latihan": "hipertrofi", "frekuensi_tersedia": 5}'
    result = _parse_json_response(raw, context="test")
    assert result == {"tujuan_latihan": "hipertrofi", "frekuensi_tersedia": 5}
    print("  ok  JSON valid ke-parse langsung tanpa perlu fallback")


def test_json_koma_ilang_kebetulin_repair():
    raw = """{
      "tujuan_latihan": "penurunan berat badan"
      "frekuensi_tersedia": 3,
      "level_pengalaman": "pemula",
      "riwayat_cedera": [],
      "catatan_tambahan": ""
    }"""
    result = _parse_json_response(raw, context="test")
    assert result["tujuan_latihan"] == "penurunan berat badan"
    assert result["frekuensi_tersedia"] == 3
    assert result["level_pengalaman"] == "pemula"
    assert result["riwayat_cedera"] == []
    print("  ok  JSON dengan koma ilang tetap berhasil di-parse lewat fallback repair")


def test_json_kebungkus_markdown_fence():
    raw = '```json\n{"tujuan_latihan": "kekuatan", "frekuensi_tersedia": 4}\n```'
    result = _parse_json_response(raw, context="test")
    assert result == {"tujuan_latihan": "kekuatan", "frekuensi_tersedia": 4}
    print("  ok  JSON yang kebungkus code fence tetap ke-parse walau diminta 'tanpa fence'")


def test_bukan_json_sama_sekali_raise_error():
    raw = "Maaf, saya tidak bisa memproses permintaan ini."
    try:
        _parse_json_response(raw, context="test")
        assert False, "Harusnya raise ValueError buat teks yang bukan JSON sama sekali"
    except ValueError as e:
        assert "test" in str(e), "Pesan error harus nyebut context-nya biar gampang di-debug"
    print("  ok  Teks yang bukan JSON sama sekali raise ValueError yang jelas (bukan crash diam-diam)")


if __name__ == "__main__":
    tests = [
        test_json_valid_langsung_parse,
        test_json_koma_ilang_kebetulin_repair,
        test_json_kebungkus_markdown_fence,
        test_bukan_json_sama_sekali_raise_error,
    ]
    print(f"Menjalankan {len(tests)} test...\n")
    for t in tests:
        t()
    print("\nSemua test lolos!")
