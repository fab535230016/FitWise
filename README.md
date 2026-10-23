# FitWise

FitWise adalah conversational agent berbahasa Indonesia yang menyusun rencana latihan beban secara personal. Setiap rekomendasi pada rencana diberi penanda sumber yang merujuk ke dokumen ilmiah pada basis pengetahuan, sehingga asal anjurannya dapat ditelusuri oleh pengguna.

Repositori ini berisi program skripsi "FitWise: Personalisasi Program Latihan Beban Melalui Conversational Agent Berbasis Retrieval sebagai Alternatif Konsultasi Personal Trainer", Fakultas Teknologi Informasi, Universitas Tarumanagara.

## Cara kerja

Satu permintaan diproses oleh lima modul secara berurutan.

1. Dialogue Analyzer mengambil profil pengguna dari percakapan bebas. Slot wajibnya adalah tujuan latihan, frekuensi per minggu, level pengalaman, riwayat cedera, dan usia, sedangkan jenis kelamin dan berat badan dicatat bila disebutkan. Slot yang masih kosong ditanyakan, lalu ringkasan profil dikonfirmasi ke pengguna sebelum rencana disusun.
2. Retrieval mencari dokumen di ChromaDB memakai BGE-M3. Dokumen inti selalu disertakan, ditambah paling banyak empat dokumen lain yang paling dekat dengan profil pengguna. Dokumen terpilih dibangun ulang secara utuh sebagai konteks.
3. Plan Generator menyusun rencana memakai Gemini 3.1 Flash Lite. Setiap kalimat rekomendasi diberi penanda sumber seperti [S1].
4. Compliance Checker memeriksa rencana terhadap riwayat cedera. Rencana yang melanggar disusun ulang, paling banyak dua kali.
5. Penyajian Hasil memetakan penanda ke berkas sumber, menghitung proporsi kalimat bersumber, dan melampirkan ilustrasi gerakan dari katalog.

Pengguna yang berusia di bawah 18 tahun tidak dilayani.

## Struktur folder

| Lokasi | Isi |
|---|---|
| `src/` | Modul inti: konfigurasi, pemecahan dokumen, ingest, retrieval, pemanggilan Gemini, pengelolaan slot, penanda sumber, katalog gerakan, dan pipeline |
| `web/` | Peladen FastAPI (`app.py`), pengelolaan sesi, perekaman umpan balik, dan halaman web di `web/static/` |
| `evaluation/` | Skrip evaluasi RAGAs dan evaluasi percakapan, data skenario, serta hasilnya di `evaluation/results/` |
| `scripts/` | Penyusun katalog gerakan, jejak perhitungan Lampiran 1, analisis jarak dokumen, daftar model Gemini, dan pembuat borang penilaian |
| `tests/` | Pengujian unit (pytest) dan pengujian halaman web (Node.js dengan jsdom) |
| `data/knowledge_base/` | Sembilan artikel ilmiah dalam format PDF |
| `data/chroma_db/` | Indeks ChromaDB hasil ingest |
| `data/gerakan/` | Katalog gerakan (`katalog_gerakan.json`) |
| `main.py` | Antarmuka baris perintah |

## Kebutuhan

- Python 3.13 (versi yang dipakai selama pengembangan)
- Kunci API Gemini dari Google AI Studio
- Koneksi internet untuk memanggil Gemini dan untuk mengunduh model BGE-M3 (sekitar 2 GB) saat pertama kali dijalankan
- Node.js, hanya untuk pengujian halaman web

## Instalasi

```
git clone https://github.com/fab535230016/FitWise.git
cd FitWise
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Di Linux atau macOS, lingkungan virtual diaktifkan dengan `source venv/bin/activate`.

Salin `.env.example` menjadi `.env`, lalu isi kunci API:

```
GEMINI_API_KEY=isi_dengan_kunci_api
```

## Menyiapkan data

Indeks pada `data/chroma_db/` dan katalog pada `data/gerakan/` sudah disertakan. Dua perintah berikut hanya perlu dijalankan ulang bila isi `data/knowledge_base/` atau `scripts/metadata_gerakan.py` diubah.

```
python -m src.ingest
python -m scripts.siapkan_gerakan
```

Ingest membaca PDF pada `data/knowledge_base/`, memecahnya menjadi potongan berukuran 800 karakter dengan overlap 150 karakter, membuang potongan yang berisi daftar pustaka, lalu menyimpan hasilnya ke ChromaDB. Dengan sembilan dokumen saat ini, indeks berisi 774 potongan.

## Menjalankan

Aplikasi web:

```
uvicorn web.app:app
```

Setelah itu buka `http://127.0.0.1:8000`. Peladen memuat BGE-M3 satu kali saat dinyalakan, jadi tunggu sampai status pada halaman menunjukkan siap.

Antarmuka baris perintah:

```
python main.py
```

Perintah yang tersedia adalah `/reset`, `/profil`, `/bantuan`, dan `exit`.

## Pengujian

```
pytest
npm install
node tests/uji_layar_pemuatan.js
node tests/uji_penanda_sumber.js
node tests/uji_peraga_gerakan.js
```

Pengujian berjalan tanpa kunci API karena pemanggilan model bahasa diganti fungsi tiruan. Pada versi ini pytest menjalankan 119 kasus uji, dan ketiga skrip jsdom memeriksa 44 pernyataan.

## Evaluasi

```
python -m evaluation.run_eval
python -m evaluation.run_dialogue_eval
```

`run_eval.py` menjalankan dua belas skenario pada tiga lengan, yaitu rag, context_only, dan baseline, lalu menilai Faithfulness dan ResponseGroundedness dengan RAGAs 0.3.9. Satu putaran penuh membutuhkan sekitar dua ratus pemanggilan model, dengan jeda 30 detik antarpemanggilan. Hasil disimpan setiap kali satu skenario selesai, dan skenario yang sudah tuntas tidak diulang selama kodenya belum berubah. Bila kuota harian habis di tengah jalan, jalankan perintah yang sama setelah kuota pulih.

`run_dialogue_eval.py` mengukur ketepatan Dialogue Analyzer pada enam belas kasus percakapan berlabel dengan total 32 giliran.

Hasil yang tersimpan di `evaluation/results/` (putaran 27 September 2026):

| Lengan | Konteks | Instruksi grounding | Faithfulness | Groundedness |
|---|---|---|---|---|
| rag | ya | ya | 0,3194 | 0,8750 |
| context_only | ya | tidak | 0,1981 | 0,7708 |
| baseline | tidak | tidak | 0,0402 | 0,4167 |

Model penilai sama dengan model penyusun, yaitu Gemini 3.1 Flash Lite, sehingga skor tersebut merupakan evaluasi diri dan berpotensi bias. Evaluasi percakapan menghasilkan 224 dari 224 slot benar.

## Konfigurasi

Seluruh parameter ada di `src/config.py`, antara lain model bahasa, ukuran potongan, jumlah dokumen tambahan, temperature dan seed tiap modul, serta lengan evaluasi. Model cadangan `gemini-3.6-flash` hanya dipakai aplikasi web, sedangkan skrip evaluasi mematikannya. Daftar model yang tersedia untuk kunci API yang dipakai dapat dilihat dengan `python -m scripts.daftar_model`.

## API

| Metode | Alamat | Fungsi |
|---|---|---|
| GET | `/` | Halaman utama |
| POST | `/api/chat` | Satu giliran percakapan |
| POST | `/api/reset` | Memulai sesi baru |
| POST | `/api/feedback` | Menyimpan umpan balik |
| GET | `/api/feedback/summary` | Ringkasan umpan balik |
| GET | `/api/ulasan` | Ulasan yang disetujui pemiliknya |
| GET | `/api/health` | Status kesiapan peladen |
| GET | `/api/knowledge-base` | Ringkasan isi basis pengetahuan |
| GET | `/api/katalog-gerakan` | Ringkasan katalog gerakan |

## Sumber data

Basis pengetahuan berisi sembilan artikel ilmiah open access berbahasa Inggris.

| Berkas | Topik |
|---|---|
| `american_college_of_sports_medicine_position.21.pdf` | Prinsip preskripsi latihan beban (dokumen inti) |
| `ijerph-19-12710.pdf` | Cedera umum di pusat kebugaran |
| `fbioe-13-1560597.pdf` | Nyeri bahu |
| `s13102-025-01297-x.pdf` | Nyeri lutut |
| `fresc-6-1641054.pdf` | Nyeri lutut |
| `jcm-10-03968-v2.pdf` | Nyeri siku |
| `journal.pone.0262023.pdf` | Cedera pergelangan kaki |
| `s10926-023-10124-4.pdf` | Nyeri punggung bawah |
| `s11332-026-01650-8.pdf` | Perbedaan respons latihan antara laki-laki dan perempuan |

Gambar dan data kelompok otot pada katalog gerakan diambil dari [free-exercise-db](https://github.com/yuhonas/free-exercise-db), yang mencantumkan lisensi Unlicense menurut pernyataan pengunggahnya. Nama, alias, langkah pelaksanaan, dan poin kunci berbahasa Indonesia ditulis sendiri di `scripts/metadata_gerakan.py`.

## Batasan

- FitWise tidak menggantikan tenaga medis atau fisioterapis. Riwayat cedera dipakai sebagai batasan keamanan, bukan sebagai diagnosis.
- Basis pengetahuan belum memuat dokumen tentang cedera pergelangan tangan dan leher.
- Ilustrasi gerakan juga dapat muncul untuk gerakan yang disebut perlu dihindari.
- Balasan singkat yang berisi pembenaran sekaligus koreksi, misalnya "oke tapi 4 hari", masih dianggap sebagai konfirmasi.

## Penulis

Fablius Maxleon, Fakultas Teknologi Informasi, Universitas Tarumanagara. Dosen pembimbing: Tri Sutrisno.
