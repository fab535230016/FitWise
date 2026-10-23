"""CLI untuk menjalankan pipeline secara interaktif."""

import os

from src.config import validate_config
from src.dialogue_state import (
    DISPLAY_FIELDS,
    FIELD_LABELS,
    REQUIRED_FIELDS,
    format_field,
)
from src.pipeline import TrainingPlanPipeline

HELP_TEXT = """
Perintah yang tersedia:
  /reset   mulai percakapan baru dari awal
  /profil  tampilkan informasi yang sudah tercatat
  /bantuan tampilkan pesan ini
  exit     keluar
"""


def print_profile(profile: dict) -> None:
    print("\nYang sudah tercatat:")
    for field in DISPLAY_FIELDS:
        tanda = "" if field in REQUIRED_FIELDS else "  (opsional)"
        print(f"  {FIELD_LABELS[field]:<22}: {format_field(profile, field)}{tanda}")
    print()


def main():
    warnings = validate_config()
    for w in warnings:
        print(f"Peringatan: {w}")
    if warnings:
        print()

    print("Conversational Agent Penyusun Rencana Latihan")

    pipeline = TrainingPlanPipeline()

    print("Menyiapkan model embedding (sekali saja, mohon tunggu)...", flush=True)
    try:
        pipeline.retriever._ensure_model_loaded()
        jumlah = pipeline.retriever.collection_count()
        print(f"Siap. Basis pengetahuan memuat {jumlah} potongan.")
    except Exception as e:
        print(f"Gagal menyiapkan retriever: {e}")
        print("Pastikan 'python3 -m src.ingest' sudah dijalankan.")
        return

    print(HELP_TEXT)
    print("AI: Halo! Kamu mau program latihan seperti apa?\n")

    while True:
        try:
            user_message = input("Kamu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSampai jumpa.")
            break

        if not user_message:
            continue

        perintah = user_message.lower()
        if perintah in {"exit", "quit", "keluar"}:
            break
        if perintah == "/bantuan":
            print(HELP_TEXT)
            continue
        if perintah == "/profil":
            print_profile(pipeline.profile)
            continue
        if perintah == "/reset":
            pipeline.reset()
            print("\nPercakapan direset.\n")
            print("AI: Halo! Kamu mau program latihan seperti apa?\n")
            continue

        try:
            result = pipeline.run(user_message)
        except Exception as e:
            print(f"\nGagal memproses: {e}\n")
            terisi = [k for k in REQUIRED_FIELDS
                      if pipeline.profile.get(k) is not None]
            if terisi:
                print(f"Informasi yang sudah kamu berikan masih tersimpan "
                      f"({len(terisi)} dari {len(REQUIRED_FIELDS)} terisi). "
                      f"Ketik apa saja untuk "
                      f"mencoba lagi, /profil untuk memeriksanya, atau /reset "
                      f"untuk mulai dari awal.\n")
            continue

        if result.status != "rencana_siap":
            print(f"\nAI: {result.message}\n")
            continue

        print(f"\nAI: {result.plan}\n")

        if not result.compliance.get("patuh", True):
            print(f"Catatan compliance: {result.compliance.get('pelanggaran')}\n")

        for w in result.warnings:
            print(f"{w}\n")

        if os.environ.get("DEBUG"):
            print(f"[debug] profil: {result.extracted_profile}")
            print(f"[debug] sumber retrieval: "
                  f"{result.retrieved_sources or '(tidak ada)'}\n")


if __name__ == "__main__":
    main()
