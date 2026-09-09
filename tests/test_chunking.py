"""
Unit test untuk chunking.py. Jalankan dengan:
    python3 -m pytest tests/test_chunking.py -v
atau langsung:
    python3 tests/test_chunking.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.chunking import chunk_text, Chunk


SAMPLE_TEXT = """Latihan resistance training adalah salah satu metode yang paling efektif untuk meningkatkan kekuatan otot. Berbagai penelitian menunjukkan bahwa volume latihan mingguan berkorelasi positif dengan hipertrofi otot hingga titik tertentu.

Pada kasus cedera bahu, khususnya rotator cuff, latihan overhead press sebaiknya dihindari pada fase awal pemulihan. Sebagai gantinya, latihan seperti front raise dengan beban ringan dan rentang gerak terbatas lebih disarankan.

Untuk cedera lutut seperti patellofemoral pain syndrome, latihan penguatan quadriceps tetap direkomendasikan, namun perlu memperhatikan sudut fleksi lutut untuk menghindari tekanan berlebih pada patela.

Prinsip progressive overload tetap menjadi dasar dalam penyusunan program latihan, baik untuk populasi sehat maupun populasi dengan riwayat cedera, dengan penyesuaian intensitas dan volume yang sesuai."""


def test_chunk_text_returns_chunks():
    chunks = chunk_text(SAMPLE_TEXT, source="test_doc.txt", chunk_size=300, chunk_overlap=50)
    assert len(chunks) > 0, "Harus menghasilkan minimal 1 chunk"
    assert all(isinstance(c, Chunk) for c in chunks)
    print(f"  ok  Menghasilkan {len(chunks)} chunk dari teks contoh")


def test_chunk_respects_max_size_roughly():
    chunks = chunk_text(SAMPLE_TEXT, source="test_doc.txt", chunk_size=300, chunk_overlap=50)
    for c in chunks:
        assert len(c.text) <= 300 + 100, f"Chunk kepanjangan: {len(c.text)} chars"
    print(f"  ok  Semua chunk masih dalam batas wajar ukurannya")


def test_chunk_metadata_preserved():
    chunks = chunk_text(
        SAMPLE_TEXT,
        source="bonilla_2022.pdf",
        chunk_size=300,
        chunk_overlap=50,
        extra_metadata={"topik": "cedera_bahu_lutut", "tahun": 2022},
    )
    assert all(c.source == "bonilla_2022.pdf" for c in chunks)
    assert all(c.metadata.get("tahun") == 2022 for c in chunks)
    print(f"  ok  Metadata (source, tahun, topik) konsisten di semua chunk")


def test_chunk_index_sequential():
    chunks = chunk_text(SAMPLE_TEXT, source="test_doc.txt", chunk_size=300, chunk_overlap=50)
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks))), "chunk_index harus urut 0,1,2,..."
    print(f"  ok  chunk_index urut: {indices}")


def test_overlap_actually_overlaps():
    """Cek bahwa ekor chunk sebelumnya muncul juga di awal chunk berikutnya."""
    chunks = chunk_text(SAMPLE_TEXT, source="test_doc.txt", chunk_size=250, chunk_overlap=60)
    if len(chunks) < 2:
        print(" Skip: teks contoh terlalu pendek buat cek overlap multi-chunk")
        return
    tail_prev = chunks[0].text[-30:]
    assert tail_prev[:15] in chunks[1].text, "Overlap kayaknya nggak jalan"
    print(f"  ok  Overlap antar chunk terverifikasi")


if __name__ == "__main__":
    tests = [
        test_chunk_text_returns_chunks,
        test_chunk_respects_max_size_roughly,
        test_chunk_metadata_preserved,
        test_chunk_index_sequential,
        test_overlap_actually_overlaps,
    ]
    print(f"Menjalankan {len(tests)} test...\n")
    for t in tests:
        t()
    print("\nSemua test lolos!")
