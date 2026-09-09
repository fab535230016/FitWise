"""
Dataset skenario uji buat evaluasi RAGAs (Faithfulness & Groundedness),
bandingin sistem RAG vs baseline non-retrieval.

Tiap skenario sengaja ditulis sebagai SATU pesan yang udah lengkap (nyebut
tujuan, frekuensi, level, dan status cedera sekaligus) supaya dialogue
analyzer bisa langsung isi semua slot wajib dalam 1 giliran -- nggak perlu
simulasi percakapan multi-turn buat evaluasi otomatis ini. Ini pilihan
desain yang disengaja: fokusnya evaluasi kualitas PLAN GENERATOR (RAG vs
baseline), bukan evaluasi dialogue analyzer/slot-filling (itu sudah dites
terpisah di tests/test_dialogue_state.py).

Cakupan yang sengaja divariasikan:
- tujuan: hipertrofi, kekuatan, penurunan berat badan
- level: pemula, menengah, lanjutan
- cedera: tidak ada, 1 cedera per lokasi tubuh yang ada di knowledge base,
  serta 1 skenario dengan 2 cedera sekaligus (uji retrieval multi-dokumen)

Catatan buat metodologi skripsi: jumlah skenario (12) sengaja dijaga kecil
tapi representatif -- sebanding dengan ukuran knowledge base (6-7 paper),
bukan skala produksi. Kalau reviewer/dosbing minta lebih banyak variasi,
tinggal tambah entri baru ke list SCENARIOS di bawah, formatnya konsisten.
"""

SCENARIOS: list[dict] = [
    {
        "id": "S01_hipertrofi_tanpa_cedera",
        "message": (
            "Aku mau program buat nambah otot (hipertrofi), levelku menengah, "
            "bisa latihan 4 hari seminggu, gak ada riwayat cedera."
        ),
    },
    {
        "id": "S02_kekuatan_pemula_tanpa_cedera",
        "message": (
            "Aku pemula banget baru mulai angkat beban, tujuannya nambah "
            "kekuatan, bisa latihan 3 hari seminggu, sehat gak ada cedera apa-apa."
        ),
    },
    {
        "id": "S03_penurunan_bb_tanpa_cedera",
        "message": (
            "Mau program buat nurunin berat badan, levelku menengah, sanggup "
            "latihan 5 hari seminggu, gak ada cedera."
        ),
    },
    {
        "id": "S04_hipertrofi_cedera_lutut",
        "message": (
            "Tujuan aku hipertrofi, level menengah, latihan 4x seminggu, ada "
            "riwayat cedera lutut kanan (patellofemoral pain)."
        ),
    },
    {
        "id": "S05_kekuatan_cedera_bahu",
        "message": (
            "Aku mau fokus nambah kekuatan, levelnya lanjutan, latihan 5 hari "
            "seminggu, ada riwayat cedera bahu / rotator cuff."
        ),
    },
    {
        "id": "S06_penurunan_bb_cedera_punggung",
        "message": (
            "Mau nurunin berat badan, pemula, bisa latihan 3 hari seminggu, "
            "ada riwayat nyeri punggung bawah kronis."
        ),
    },
    {
        "id": "S07_hipertrofi_cedera_pergelangan_kaki",
        "message": (
            "Tujuan hipertrofi, level menengah, latihan 4 hari seminggu, "
            "pernah cedera pergelangan kaki (ankle sprain) beberapa bulan lalu."
        ),
    },
    {
        "id": "S08_kekuatan_multi_cedera",
        "message": (
            "Aku mau nambah kekuatan, level lanjutan, latihan 5 hari seminggu, "
            "ada riwayat cedera lutut kiri DAN cedera bahu kanan."
        ),
    },
    {
        "id": "S09_hipertrofi_pemula_cedera_umum",
        "message": (
            "Pemula, tujuannya hipertrofi, baru sanggup 2 hari seminggu, "
            "sering ngerasa nyeri di beberapa sendi pas latihan beban tapi "
            "gak tau spesifik dimana."
        ),
    },
    {
        "id": "S10_kekuatan_lanjutan_tanpa_cedera",
        "message": (
            "Level aku udah lanjutan, tujuannya kekuatan maksimal, latihan "
            "6 hari seminggu, kondisi fisik sehat semua."
        ),
    },
    {
        "id": "S11_penurunan_bb_cedera_lutut",
        "message": (
            "Mau nurunin berat badan, level menengah, latihan 4 hari seminggu, "
            "ada riwayat nyeri lutut anterior pas naik turun tangga."
        ),
    },
    {
        "id": "S12_hipertrofi_cedera_bahu_pemula",
        "message": (
            "Aku pemula, mau nambah otot terutama upper body, latihan 3 hari "
            "seminggu, ada keluhan bahu suka sakit kalau angkat tangan tinggi-tinggi."
        ),
    },
]
