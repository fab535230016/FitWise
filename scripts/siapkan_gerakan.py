"""Bangun katalog ilustrasi gerakan dan unduh gambarnya.

Katalog menggabungkan dua hal:

1. Metadata berbahasa Indonesia yang ditulis manual pada
   `scripts/metadata_gerakan.py` (nama, alias, pola gerak, langkah, poin kunci).
2. Data terbuka dari free-exercise-db (kelompok otot, alat, dan berkas gambar).

free-exercise-db mencantumkan lisensi Unlicense pada repositorinya. Perlu
dicatat bahwa lisensi itu dinyatakan sendiri oleh pengunggah repositori, dan
baik free-exercise-db maupun sumber hulunya (wrkout/exercises.json) tidak
menjelaskan asal-usul fotonya. Karena itu katalog menyimpan lisensi sebagai
klaim, bukan sebagai fakta yang sudah diverifikasi, dan rujukannya ditampilkan
di antarmuka agar pembaca dapat menelusurinya sendiri.

Pemakaian:

    python3 -m scripts.siapkan_gerakan                  # katalog + unduh gambar
    python3 -m scripts.siapkan_gerakan --tanpa-gambar   # katalog saja
    python3 -m scripts.siapkan_gerakan --paksa          # timpa gambar yang ada
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.metadata_gerakan import GERAKAN  # noqa: E402
from src.exercise_media import normalisasi  # noqa: E402

SUMBER_DATA = (
    "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
)
SUMBER_GAMBAR = (
    "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"
)
LISENSI = "Unlicense (menurut pernyataan pengunggah)"
BERANDA_SUMBER = "https://github.com/yuhonas/free-exercise-db"

KATALOG_PATH = BASE_DIR / "data" / "gerakan" / "katalog_gerakan.json"
GAMBAR_DIR = BASE_DIR / "web" / "static" / "gerakan"

OTOT_INDONESIA = {
    "abdominals": "perut",
    "abductors": "abduktor pinggul",
    "adductors": "adduktor paha",
    "biceps": "bisep",
    "calves": "betis",
    "chest": "dada",
    "forearms": "lengan bawah",
    "glutes": "gluteus (bokong)",
    "hamstrings": "hamstring (paha belakang)",
    "lats": "latissimus (punggung samping)",
    "lower back": "punggung bawah",
    "middle back": "punggung tengah",
    "neck": "leher",
    "quadriceps": "kuadrisep (paha depan)",
    "shoulders": "bahu",
    "traps": "trapezius",
    "triceps": "trisep",
}

ALAT_INDONESIA = {
    "barbell": "barbel",
    "dumbbell": "dumbel",
    "cable": "katrol",
    "machine": "mesin",
    "body only": "berat badan sendiri",
    "kettlebells": "kettlebell",
    "bands": "karet resistensi",
    "medicine ball": "bola medis",
    "exercise ball": "bola latihan",
    "e-z curl bar": "barbel EZ",
    "foam roll": "foam roll",
    "other": "alat lain",
    None: "tidak ditentukan",
}


def unduh_teks(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as respons:
        return respons.read().decode("utf-8")


def unduh_biner(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as respons:
        return respons.read()


def terjemahkan(daftar: list[str], kamus: dict) -> list[str]:
    return [kamus.get(item, item) for item in daftar or []]


def bangun_katalog(sumber: list[dict]) -> list[dict]:
    berdasarkan_nama = {item["name"]: item for item in sumber}
    katalog: list[dict] = []
    hilang: list[str] = []

    for meta in GERAKAN:
        asal = berdasarkan_nama.get(meta["sumber_nama"])
        if asal is None:
            hilang.append(meta["sumber_nama"])
            continue

        gambar = list(asal.get("images") or [])
        katalog.append(
            {
                "id": meta["id"],
                "nama": meta["nama"],
                "nama_id": meta["nama_id"],
                "pola_gerak": meta["pola_gerak"],
                # Alias disimpan dalam bentuk yang sudah dinormalkan supaya
                # penulisan yang setara ("push-up", "push up", "pushup") tidak
                # tersimpan berkali-kali.
                "alias": sorted(
                    {normalisasi(a) for a in meta["alias"] if normalisasi(a)},
                    key=len,
                    reverse=True,
                ),
                "kelompok_otot_utama": terjemahkan(
                    asal.get("primaryMuscles"), OTOT_INDONESIA
                ),
                "kelompok_otot_pendukung": terjemahkan(
                    asal.get("secondaryMuscles"), OTOT_INDONESIA
                ),
                "alat": ALAT_INDONESIA.get(asal.get("equipment"), asal.get("equipment")),
                "langkah": meta["langkah"],
                "poin_kunci": meta["poin_kunci"],
                "gambar": [
                    {
                        "berkas": f"{meta['id']}/{urutan}.jpg",
                        "asal": f"{SUMBER_GAMBAR}{jalur}",
                        "keterangan": (
                            "Posisi awal" if urutan == 0 else "Posisi akhir"
                        ),
                    }
                    for urutan, jalur in enumerate(gambar)
                ],
                "sumber_media": {
                    "nama": "free-exercise-db",
                    "id_asal": asal.get("id"),
                    "lisensi": LISENSI,
                    "url": BERANDA_SUMBER,
                },
            }
        )

    if hilang:
        print("Peringatan: nama sumber berikut tidak ditemukan di free-exercise-db:")
        for nama in hilang:
            print(f"  - {nama}")

    return katalog


def periksa_alias_bentrok(katalog: list[dict]) -> None:
    """Peringatkan jika satu alias dipakai oleh lebih dari satu gerakan."""
    pemilik: dict[str, str] = {}
    for entri in katalog:
        for alias in entri["alias"]:
            if alias in pemilik and pemilik[alias] != entri["id"]:
                print(
                    f"Peringatan: alias '{alias}' dipakai oleh "
                    f"'{pemilik[alias]}' dan '{entri['id']}'."
                )
            pemilik[alias] = entri["id"]


def unduh_gambar(katalog: list[dict], paksa: bool = False) -> tuple[int, int]:
    baru = 0
    lewat = 0
    for entri in katalog:
        for gambar in entri["gambar"]:
            tujuan = GAMBAR_DIR / gambar["berkas"]
            if tujuan.exists() and not paksa:
                lewat += 1
                continue
            tujuan.parent.mkdir(parents=True, exist_ok=True)
            try:
                tujuan.write_bytes(unduh_biner(gambar["asal"]))
                baru += 1
                print(f"  unduh {gambar['berkas']}")
            except urllib.error.URLError as galat:
                print(f"  gagal {gambar['berkas']}: {galat}")
    return baru, lewat


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tanpa-gambar",
        action="store_true",
        help="hanya bangun berkas katalog, jangan unduh gambar",
    )
    parser.add_argument(
        "--paksa",
        action="store_true",
        help="unduh ulang gambar yang sudah ada",
    )
    argumen = parser.parse_args()

    print(f"Mengambil data gerakan dari {SUMBER_DATA}")
    sumber = json.loads(unduh_teks(SUMBER_DATA))
    print(f"  {len(sumber)} gerakan tersedia pada sumber.")

    katalog = bangun_katalog(sumber)
    periksa_alias_bentrok(katalog)

    KATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    KATALOG_PATH.write_text(
        json.dumps(
            {
                "versi": 1,
                "lisensi_media": LISENSI,
                "sumber_media": BERANDA_SUMBER,
                "basis_url_media": SUMBER_GAMBAR,
                "gerakan": katalog,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Katalog tersimpan: {KATALOG_PATH} ({len(katalog)} gerakan)")

    if argumen.tanpa_gambar:
        print("Pengunduhan gambar dilewati (--tanpa-gambar).")
        return 0

    print(f"Mengunduh gambar ke {GAMBAR_DIR}")
    baru, lewat = unduh_gambar(katalog, paksa=argumen.paksa)
    print(f"Selesai. {baru} gambar diunduh, {lewat} dilewati karena sudah ada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
