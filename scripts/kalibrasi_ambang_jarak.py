"""Kalibrasi ambang jarak untuk jalur retrieval kondisional.

Skrip ini tidak memanggil model bahasa sama sekali. Profil tiap skenario
dibaca dari hasil evaluasi yang sudah ada, lalu query retrieval dibangun
ulang persis seperti yang dilakukan pipeline. Keluarannya adalah jarak
setiap dokumen kandidat, sebagai dasar memilih ambang secara empiris
alih-alih menebak.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config
from src.pipeline import TrainingPlanPipeline
from src.retriever import Retriever

ARSIP = Path("evaluation/results/arsip_run1_tanpa_ambang/ragas_eval_results.json")
UTAMA = Path("evaluation/results/ragas_eval_results.json")


def muat_profil() -> list[tuple[str, dict]]:
    sumber = ARSIP if ARSIP.exists() else UTAMA
    data = json.loads(sumber.read_text(encoding="utf-8"))
    print(f"Profil dibaca dari: {sumber}\n")
    return [(s["scenario_id"], s["extracted_profile"]) for s in data["hasil"]]


def main() -> None:
    retriever = Retriever()
    semua = retriever.list_all_sources()
    inti = [s for s in semua if retriever._is_core_document(s)]
    print(f"Dokumen inti (selalu ikut): {inti}")
    print(f"Total dokumen di basis pengetahuan: {len(semua)}\n")

    jarak_terpakai: list[float] = []
    jarak_terbuang: list[float] = []

    for sid, profil in muat_profil():
        query = TrainingPlanPipeline._build_retrieval_query(profil)
        hits = retriever.retrieve(query, top_k=config.TOP_K_CHUNKS_FOR_RANKING)

        terbaik: dict[str, float] = {}
        for c in hits:
            if c.source in inti:
                continue
            if c.source not in terbaik:
                terbaik[c.source] = c.distance

        urut = sorted(terbaik.items(), key=lambda kv: kv[1])
        cedera = profil.get("riwayat_cedera") or []
        print(f"[{sid}]")
        print(f"  query  : {query}")
        print(f"  cedera : {cedera if cedera else 'tidak ada'}")
        for peringkat, (sumber, d) in enumerate(urut, start=1):
            masuk = peringkat <= config.MAX_CONDITIONAL_DOCUMENTS
            tanda = "DIPAKAI" if masuk else "dibuang"
            (jarak_terpakai if masuk else jarak_terbuang).append(d)
            print(f"    {tanda:8} {d:.4f}  {sumber}")
        print()

    print("=" * 62)
    if jarak_terpakai:
        jarak_terpakai.sort()
        print(f"Dokumen yang DIPAKAI  : n={len(jarak_terpakai)}  "
              f"min={jarak_terpakai[0]:.4f}  "
              f"median={jarak_terpakai[len(jarak_terpakai) // 2]:.4f}  "
              f"maks={jarak_terpakai[-1]:.4f}")
    if jarak_terbuang:
        jarak_terbuang.sort()
        print(f"Dokumen yang dibuang  : n={len(jarak_terbuang)}  "
              f"min={jarak_terbuang[0]:.4f}  maks={jarak_terbuang[-1]:.4f}")

    print("\nSimulasi berbagai ambang (berapa dokumen kondisional tersisa):")
    for ambang in (0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80, 0.90, 1.00):
        sisa = sum(1 for d in jarak_terpakai if d <= ambang)
        print(f"  ambang {ambang:.2f} -> {sisa:2d} dari {len(jarak_terpakai)} "
              f"dokumen yang sekarang dipakai tetap lolos")


if __name__ == "__main__":
    main()
