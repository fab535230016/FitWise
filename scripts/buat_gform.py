"""Bangun skrip Google Form FitWise dari hasil evaluasi RAGAs.

Menulis gform/form_fitwise.gs dan gform/rencana_dinilai.csv. Rencana untuk
form penilaian diambil dari lengan rag pada
evaluation/results/ragas_eval_results.json untuk tiga skenario pada
SKENARIO_DINILAI, satu untuk tiap tujuan latihan dengan level dan area cedera
yang berbeda. Penanda sumbernya dibuang memakai strip_source_markers.
Diagram temuan kuesioner (gform/grafik/temuan-N.png) dan tangkapan layar
aplikasi (gform/grafik/aplikasi-N-judul.png) ditanam sebagai base64 sehingga
form tidak memerlukan unggahan gambar ke Google Drive.

Pemakaian:
    python scripts/buat_gform.py
    python scripts/buat_gform.py --izinkan-belum-lengkap
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.citations import strip_source_markers
from evaluation.scenarios import SCENARIOS

HASIL = ROOT / "evaluation" / "results" / "ragas_eval_results.json"
TEMPLAT = ROOT / "gform" / "form_fitwise.template.gs"
KELUARAN = ROOT / "gform" / "form_fitwise.gs"
RINGKASAN = ROOT / "gform" / "rencana_dinilai.csv"
LENGAN = "rag"
SKENARIO_DINILAI = [
    "S04_hipertrofi_cedera_lutut",
    "S05_kekuatan_cedera_bahu",
    "S06_penurunan_bb_cedera_punggung",
]
PENANDA_DATA = "/*__DATA_RENCANA__*/"
PENANDA_GRAFIK = "/*__GRAFIK_TEMUAN__*/"
FOLDER_GRAFIK = ROOT / "gform" / "grafik"
POLA_GRAFIK = re.compile(r"^temuan-(\d+)\.png$")
POLA_APLIKASI = re.compile(r"^(aplikasi-(\d+)-[\w-]+)\.png$")
SISA_PENANDA = re.compile(r"\[\s*S\s*\d")


def angka(nilai):
    if isinstance(nilai, (int, float)) and math.isfinite(nilai):
        return nilai
    return None


def profil_dari(p: dict) -> dict:
    return {
        "tujuan": p.get("tujuan_latihan") or "-",
        "frekuensi": p.get("frekuensi_tersedia") or "-",
        "level": p.get("level_pengalaman") or "-",
        "cedera": list(p.get("riwayat_cedera") or []),
        "usia": p.get("usia") or "-",
        "jenisKelamin": p.get("jenis_kelamin"),
        "beratBadan": p.get("berat_badan"),
        "catatan": (p.get("catatan_tambahan") or "").strip(),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--izinkan-belum-lengkap", action="store_true",
                    help="tetap menulis skrip walau skenario yang dinilai belum ada; "
                         "form akan menolak dibuat")
    args = ap.parse_args()

    with open(HASIL, encoding="utf-8") as f:
        hasil = json.load(f)
    per_skenario = {r["scenario_id"]: r for r in hasil.get("hasil", [])}

    dikenal = {s["id"] for s in SCENARIOS}
    asing = [sid for sid in SKENARIO_DINILAI if sid not in dikenal]
    if asing:
        sys.exit(f"Skenario tidak dikenal pada SKENARIO_DINILAI: {', '.join(asing)}")
    hilang = [sid for sid in SKENARIO_DINILAI if sid not in per_skenario]
    lengkap = not hilang
    if not lengkap and not args.izinkan_belum_lengkap:
        sys.exit(
            f"Skenario yang dinilai belum ada pada hasil evaluasi: {', '.join(hilang)}. "
            f"Selesaikan evaluasi dulu, atau pakai --izinkan-belum-lengkap untuk "
            f"menyiapkan skrip tanpa data rencana."
        )

    rencana = []
    for sid in SKENARIO_DINILAI:
        r = per_skenario.get(sid)
        if r is None:
            continue
        a = r["arms"][LENGAN]
        teks = strip_source_markers(a["plan"])
        if not teks or SISA_PENANDA.search(teks):
            sys.exit(f"Rencana {sid} lengan {LENGAN} kosong atau masih memuat penanda sumber.")
        rencana.append({
            "nomor": len(rencana) + 1,
            "skenario": sid,
            "lengan": LENGAN,
            "profil": profil_dari(r["extracted_profile"]),
            "rencana": teks,
            "faithfulness": angka(a.get("faithfulness")),
            "groundedness": angka(a.get("groundedness")),
        })

    sidik = hasil.get("konfigurasi", {}).get("sidik_kode", {}).get("sha256", "-")
    sumber = (f"{HASIL.relative_to(ROOT).as_posix()}, dijalankan {hasil.get('dijalankan_pada')}, "
              f"sidik kode {sidik}, lengan {LENGAN}, skenario {', '.join(SKENARIO_DINILAI)}")
    data = (
        f"const DATA_LENGKAP = {'true' if lengkap else 'false'};\n"
        f"const SUMBER_DATA = {json.dumps(sumber, ensure_ascii=False)};\n"
        f"const DATA_RENCANA = {json.dumps(rencana, ensure_ascii=False, indent=1)};"
    )

    grafik, aplikasi = {}, []
    if FOLDER_GRAFIK.is_dir():
        for berkas in sorted(FOLDER_GRAFIK.iterdir()):
            b64 = lambda: base64.b64encode(berkas.read_bytes()).decode("ascii")
            cocok = POLA_GRAFIK.match(berkas.name)
            if cocok:
                grafik[str(int(cocok.group(1)))] = b64()
            cocok = POLA_APLIKASI.match(berkas.name)
            if cocok:
                aplikasi.append((int(cocok.group(2)), cocok.group(1), b64()))
    grafik = dict(sorted(grafik.items(), key=lambda kv: int(kv[0])))
    aplikasi.sort()
    data_grafik = ("const GRAFIK_TEMUAN = {\n" + "".join(
        f'  "{k}": "{v}",\n' for k, v in grafik.items()) + "};\n"
        + "const GAMBAR_APLIKASI = [\n" + "".join(
        f'  {{ nama: "{nama}", b64: "{v}" }},\n' for _, nama, v in aplikasi) + "];")

    templat = TEMPLAT.read_text(encoding="utf-8")
    for penanda in (PENANDA_DATA, PENANDA_GRAFIK):
        if templat.count(penanda) != 1:
            sys.exit(f"Penanda {penanda} tidak ditemukan tepat satu kali pada {TEMPLAT.name}.")
    KELUARAN.write_text(templat.replace(PENANDA_DATA, data).replace(PENANDA_GRAFIK, data_grafik),
                        encoding="utf-8")

    with open(RINGKASAN, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["nomor_rencana", "skenario", "lengan", "faithfulness", "groundedness"])
        for d in rencana:
            w.writerow([d["nomor"], d["skenario"], d["lengan"], d["faithfulness"], d["groundedness"]])

    print(f"Skrip form ditulis ke {KELUARAN.relative_to(ROOT)}")
    print(f"Daftar rencana yang dinilai ditulis ke {RINGKASAN.relative_to(ROOT)}")
    print(f"Rencana: {len(rencana)} dari {len(SKENARIO_DINILAI)}"
          f"{'' if lengkap else ' (BELUM LENGKAP, form akan menolak dibuat)'}")
    print(f"Tangkapan layar aplikasi: {len(aplikasi)} "
          f"({', '.join(n for _, n, _ in aplikasi) if aplikasi else 'tidak ada'})")
    print(f"Diagram temuan kuesioner: {len(grafik)} "
          f"({', '.join(grafik) if grafik else f'tidak ada berkas temuan-N.png di {FOLDER_GRAFIK.relative_to(ROOT)}'})")


if __name__ == "__main__":
    main()
