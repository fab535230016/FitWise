"""Tampilkan model yang benar-benar tersedia untuk API key pada berkas .env.

Dipakai agar nama model tidak ditebak. Keluarannya dipakai untuk mengisi
GEMINI_MODEL dan EVAL_JUDGE_MODEL di src/config.py.
"""

from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config


def main() -> None:
    from google import genai

    if not config.GEMINI_API_KEY:
        print("GEMINI_API_KEY belum diisi di .env")
        return

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    baris = []
    for m in client.models.list():
        metode = getattr(m, "supported_actions", None) or []
        if metode and "generateContent" not in metode:
            continue
        nama = m.name.removeprefix("models/")
        baris.append((nama, getattr(m, "display_name", "") or ""))

    baris.sort()
    print(f"{len(baris)} model mendukung generateContent:\n")
    for nama, tampil in baris:
        tanda = ""
        if nama == config.GEMINI_MODEL:
            tanda = "   <- penyusun sekarang"
        elif nama == config.EVAL_JUDGE_MODEL:
            tanda = "   <- penilai sekarang"
        print(f"  {nama:44} {tampil[:34]}{tanda}")

    print(f"\nPenyusun di config : {config.GEMINI_MODEL}")
    print(f"Penilai di config  : {config.EVAL_JUDGE_MODEL}")
    tersedia = {n for n, _ in baris}
    for label, nama in (("Penyusun", config.GEMINI_MODEL),
                        ("Penilai", config.EVAL_JUDGE_MODEL)):
        if nama and nama not in tersedia:
            print(f"  PERINGATAN: {label} '{nama}' TIDAK ADA di daftar di atas.")


if __name__ == "__main__":
    main()
