## Struktur Project

```
rag-project/
├── main.py                  # CLI buat testing pipeline end-to-end
├── requirements.txt
├── .env.example              # copy jadi .env, isi API key
├── src/
│   ├── config.py              # semua konfigurasi (model, path, chunk size)
│   ├── chunking.py            # pecah dokumen jadi chunk (sudah ditest)
│   ├── ingest.py               # load dokumen -> embed -> simpan ke ChromaDB
│   ├── retriever.py            # query ChromaDB, ambil chunk relevan
│   ├── generator.py            # wrapper Gemini (analyzer, plan generator,
│   │                            #   compliance checker, baseline non-RAG)
│   ├── dialogue_state.py       # slot-filling: kumpulin profil user bertahap
│   │                            #   antar pesan, cek data wajib yang kurang
│   └── pipeline.py             # orkestrasi semua di atas jadi satu alur
├── data/
│   ├── knowledge_base/         # taruh paper/pedoman (.txt atau .pdf) di sini
│   └── chroma_db/               # otomatis dibuat, tempat ChromaDB nyimpen data
└── tests/
    ├── test_chunking.py         # unit test (JALAN tanpa perlu API key/internet)
    └── test_dialogue_state.py   # unit test slot-filling (JALAN tanpa API key/internet)
```

## Alur percakapan multi-turn (slot-filling)

Awalnya tiap pesan user diproses sendiri-sendiri tanpa mengingat pesan
sebelumnya, jadi begitu user baru kasih sebagian info (misal cuma "latihan
otot 5x seminggu"), sistem tetap maksa generate rencana lengkap dengan profil
yang bolong (level pengalaman & riwayat cedera masih kosong) → hasilnya
generik/nggak nyambung ("out of context").

Sekarang `TrainingPlanPipeline` nyimpen profil user (`self.profile`) selama
sesi CLI berjalan, dan tiap pesan baru cuma **melengkapi** slot yang masih
kosong (lihat `src/dialogue_state.py`), bukan menimpa dari nol. Field wajib
sebelum boleh generate rencana: `tujuan_latihan`, `frekuensi_tersedia`,
`level_pengalaman`, `riwayat_cedera` (field terakhir ini pakai tri-state:
`null` = belum ditanya, `[]` = user eksplisit bilang nggak ada cedera, biar
nggak ketuker sama "belum jawab").

Contoh alur:

```
AI  : Halo! Kamu mau program latihan seperti apa?
Kamu: aku pengen latihan 5x seminggu latihan otot
AI  : Oke, catat ya — tujuannya hipertrofi, 5x seminggu. Sebelum aku
      susunin rencananya, boleh lengkapi dulu:
      - Level pengalaman kamu gimana — pemula, menengah, atau lanjutan?
      - Ada riwayat cedera atau keluhan fisik tertentu nggak?
Kamu: aku menengah, gak ada cedera
AI  : (baru di sini retrieval + plan generator + compliance checker jalan)
```

Kalau mau mulai sesi baru (lupain profil lama) tanpa keluar dari program,
panggil `pipeline.reset()`.

## Setup di lokal

```bash
# 1. Buat virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup API key
cp .env.example .env
# edit .env, isi GEMINI_API_KEY (gratis di https://aistudio.google.com/apikey)

# 4. Verifikasi logic chunking dulu (nggak butuh internet/API key)
python3 tests/test_chunking.py

# 5. Taruh dokumen knowledge base kamu (paper, pedoman, dst) di
#    data/knowledge_base/ sebagai .txt atau .pdf

# 6. Jalankan ingest (download model BGE-M3 pertama kali, ~2GB, bisa
#    beberapa menit)
python3 -m src.ingest

# 7. Coba pipeline end-to-end
python3 main.py
```

## Alur kerja tiap komponen

| Komponen | File | Peran |
|---|---|---|
| Dialogue Analyzer | `generator.py::analyze_dialogue` | Ekstrak tujuan, riwayat cedera, level dari pesan bebas user jadi JSON terstruktur |
| Retrieval | `retriever.py::Retriever.retrieve` | Embed query user, cari top-k chunk relevan di ChromaDB |
| Plan Generator | `generator.py::generate_plan` | Susun rencana latihan, grounded ke hasil retrieval (bukan pengetahuan bebas LLM) |
| Compliance Checker | `generator.py::check_compliance` | Validasi rencana nggak melanggar constraint (misal cedera) user |
| Baseline Non-RAG | `generator.py::generate_plan_baseline_non_rag` | Versi tanpa retrieval, buat pembanding evaluasi faithfulness/groundedness |

## Evaluasi Faithfulness & Groundedness (RAG vs Baseline)

Buat bagian "Evaluasi Faithfulness dan Groundedness terhadap Baseline
Non-Retrieval" di metodologimu, jalankan:

```bash
python3 -m evaluation.run_eval
```

Ini otomatis:
1. Jalankan 12 skenario user (`evaluation/scenarios.py`) lewat sistem RAG
   DAN baseline non-retrieval, pakai profil yang persis sama di keduanya.
2. Hitung skor **Faithfulness** dan **ResponseGroundedness** (dari
   `ragas.metrics`) untuk kedua jawaban, dinilai terhadap konteks yang SAMA
   (hasil retrieval RAG) -- biar perbandingannya adil dan bermakna secara
   metodologis (baseline sendiri nggak punya "konteks", jadi dites terhadap
   literatur yang sama yang RAG pakai).
3. Cetak ringkasan skor rata-rata RAG vs baseline ke terminal.
4. Simpan hasil lengkap ke `evaluation/results/`:
   - `ragas_eval_results.json` (semua detail: plan lengkap, sumber, skor)
   - `ragas_eval_summary.csv` (ringkasan siap ditempel ke lampiran skripsi)

**Perkiraan biaya API:** tiap skenario butuh ~9-10 panggilan Gemini
(dialogue analyzer + plan generator RAG + plan generator baseline +
compliance checker + 2 metrik RAGAs x 2 sistem). Untuk 12 skenario, total
~110 panggilan -- perhatikan quota harian Gemini kamu (lihat bagian
Troubleshooting di bawah kalau kena rate limit di tengah jalan).

Mau nambah/ubah skenario ujinya? Edit langsung `evaluation/scenarios.py`,
formatnya list of dict dengan field `id` dan `message`. Tulis tiap pesan
skenario selengkap mungkin (sebut tujuan, frekuensi, level, DAN status
cedera sekaligus) supaya dialogue analyzer bisa langsung isi semua slot
wajib dalam 1 giliran -- kalau ada skenario yang statusnya nggak
"rencana_siap" dalam 1 giliran, script bakal kasih warning di log.

## Troubleshooting umum

- **`ModuleNotFoundError: No module named 'src'`** → pastikan run dari
  root folder project (`rag-project/`), bukan dari dalam `src/`.
- **Download BGE-M3 lambat/gagal** → cek koneksi internet, atau coba set
  `HF_ENDPOINT=https://hf-mirror.com` sebagai env var kalau ada kendala
  akses HuggingFace dari Indonesia.
- **Gemini API error 429 (rate limit)** → tier gratis ada limit request/menit,
  tambahkan `time.sleep()` kalau testing banyak query sekaligus.
