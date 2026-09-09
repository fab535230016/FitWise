"""Evaluasi ketepatan Dialogue Analyzer pada percakapan bertahap."""

from __future__ import annotations
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import config, validate_config
from src.dialogue_state import INITIAL_PROFILE, REQUIRED_FIELDS, merge_profile
from src.generator import analyze_dialogue
from evaluation.dialogue_cases import DIALOGUE_CASES

SINONIM: dict[str, list[set[str]]] = {
    "tujuan_latihan": [
        {"hipertrofi", "hypertrophy", "massa otot", "pembesaran otot"},
        {"kekuatan", "strength", "kekuatan maksimal"},
        {"penurunan berat badan", "penurunan bb", "fat loss", "menurunkan berat badan"},
    ],
    "level_pengalaman": [
        {"pemula", "beginner"},
        {"menengah", "intermediate"},
        {"lanjutan", "advanced", "mahir"},
    ],
}

KATA_ABAI = {"nyeri", "sakit", "cedera", "keluhan", "riwayat", "pernah",
             "bermasalah", "pegal", "keseleo", "di", "pada", "bagian"}

SISI = {"kanan", "kiri"}


def normalkan(teks: str) -> str:
    return re.sub(r"\s+", " ", str(teks).strip().lower())


def cocok_kategori(field: str, diharapkan, diperoleh) -> bool:
    a, b = normalkan(diharapkan), normalkan(diperoleh)
    if a == b:
        return True
    for kelompok in SINONIM.get(field, []):
        if any(k in a for k in kelompok) and any(k in b for k in kelompok):
            return True
    return False


def inti_cedera(teks: str) -> set[str]:
    """Ambil kata inti sebuah keluhan, mengabaikan kata umum."""
    kata = re.findall(r"[a-z]+", normalkan(teks))
    return {k for k in kata if k not in KATA_ABAI and len(k) > 2}


def satu_cedera_cocok(a: str, b: str) -> bool:
    """Cocok bila area tubuhnya sama dan sisi tubuhnya tidak bertentangan.

    Sisi tubuh diperiksa terpisah, sebab irisan pada nama area saja akan
    menganggap "bahu kanan" sama dengan "bahu kiri".
    """
    ia, ib = inti_cedera(a), inti_cedera(b)
    area_a, area_b = ia - SISI, ib - SISI
    if not (area_a & area_b):
        return False
    sisi_a, sisi_b = ia & SISI, ib & SISI
    if sisi_a and sisi_b and sisi_a != sisi_b:
        return False
    return True


def cocok_cedera(diharapkan, diperoleh) -> bool:
    if diharapkan is None or diperoleh is None:
        return diharapkan is diperoleh
    if diharapkan == [] or diperoleh == []:
        return diharapkan == diperoleh
    if len(diharapkan) != len(diperoleh):
        return False
    sisa = list(diperoleh)
    for item in diharapkan:
        pas = next((s for s in sisa if satu_cedera_cocok(item, s)), None)
        if pas is None:
            return False
        sisa.remove(pas)
    return True


def cocok_slot(field: str, diharapkan, diperoleh) -> bool:
    if field == "riwayat_cedera":
        return cocok_cedera(diharapkan, diperoleh)
    if diharapkan is None or diperoleh is None:
        return diharapkan is None and diperoleh in (None, "tidak_disebutkan")
    if field == "frekuensi_tersedia":
        try:
            return int(diharapkan) == int(diperoleh)
        except (TypeError, ValueError):
            return False
    return cocok_kategori(field, diharapkan, diperoleh)


@dataclass
class HasilGiliran:
    giliran: int
    message: str
    diharapkan: dict
    diperoleh: dict
    slot_benar: int
    slot_dinilai: int
    profil_utuh_benar: bool
    salah: list = field(default_factory=list)


@dataclass
class HasilKasus:
    case_id: str
    keterangan: str
    giliran: list = field(default_factory=list)
    galat: str | None = None


def jalankan_kasus(kasus: dict) -> HasilKasus:
    hasil = HasilKasus(case_id=kasus["id"], keterangan=kasus["keterangan"])
    profil = dict(INITIAL_PROFILE)

    for nomor, turn in enumerate(kasus["turns"], start=1):
        try:
            diekstrak = analyze_dialogue(
                turn["message"],
                current_riwayat_cedera=profil.get("riwayat_cedera"),
            )
        except Exception as e:
            hasil.galat = f"giliran {nomor}: {e}"
            return hasil

        profil = merge_profile(profil, diekstrak)

        diharapkan = {f: turn["expected"].get(f) for f in REQUIRED_FIELDS}
        benar, salah = 0, []
        for f in REQUIRED_FIELDS:
            if cocok_slot(f, diharapkan[f], profil.get(f)):
                benar += 1
            else:
                salah.append({
                    "slot": f,
                    "diharapkan": diharapkan[f],
                    "diperoleh": profil.get(f),
                })

        hasil.giliran.append(HasilGiliran(
            giliran=nomor,
            message=turn["message"],
            diharapkan=diharapkan,
            diperoleh={f: profil.get(f) for f in REQUIRED_FIELDS},
            slot_benar=benar,
            slot_dinilai=len(REQUIRED_FIELDS),
            profil_utuh_benar=(benar == len(REQUIRED_FIELDS)),
            salah=salah,
        ))
        print(f"    giliran {nomor}: {benar}/{len(REQUIRED_FIELDS)} slot benar"
              f"{'' if not salah else '  <- ' + ', '.join(s['slot'] for s in salah)}")

        time.sleep(config.API_PACING_DELAY_SECONDS)

    return hasil


def ringkas(hasil: list[HasilKasus]) -> dict:
    semua = [g for h in hasil for g in h.giliran]
    if not semua:
        return {}

    benar = sum(g.slot_benar for g in semua)
    total = sum(g.slot_dinilai for g in semua)
    utuh = sum(1 for g in semua if g.profil_utuh_benar)

    per_slot = {}
    for f in REQUIRED_FIELDS:
        cocok = sum(1 for g in semua
                    if not any(s["slot"] == f for s in g.salah))
        per_slot[f] = round(cocok / len(semua), 4)

    return {
        "kasus": len(hasil),
        "giliran": len(semua),
        "akurasi_slot": round(benar / total, 4),
        "akurasi_profil_utuh": round(utuh / len(semua), 4),
        "akurasi_per_slot": per_slot,
        "kasus_bergalat": [h.case_id for h in hasil if h.galat],
    }


def main() -> None:
    for w in validate_config():
        print(f"Peringatan: {w}")

    print(f"Menjalankan {len(DIALOGUE_CASES)} kasus percakapan bertahap "
          f"({sum(len(k['turns']) for k in DIALOGUE_CASES)} giliran)\n")

    hasil = []
    for kasus in DIALOGUE_CASES:
        print(f"[{kasus['id']}] {kasus['keterangan']}")
        hasil.append(jalankan_kasus(kasus))

    r = ringkas(hasil)
    print("\nRINGKASAN KETEPATAN DIALOGUE ANALYZER")
    print(f"  Kasus percakapan     : {r['kasus']}")
    print(f"  Total giliran        : {r['giliran']}")
    print(f"  Akurasi slot         : {r['akurasi_slot']:.4f}")
    print(f"  Akurasi profil utuh  : {r['akurasi_profil_utuh']:.4f}")
    print("  Akurasi per slot:")
    for f, v in r["akurasi_per_slot"].items():
        print(f"    {f:<22}{v:.4f}")
    if r["kasus_bergalat"]:
        print(f"  Kasus bergalat       : {', '.join(r['kasus_bergalat'])}")

    salah = [(h.case_id, g.giliran, s)
             for h in hasil for g in h.giliran for s in g.salah]
    if salah:
        print(f"\n  Rincian {len(salah)} slot yang tidak cocok:")
        for cid, nomor, s in salah:
            print(f"    {cid} giliran {nomor}: {s['slot']} "
                  f"diharapkan={s['diharapkan']!r} diperoleh={s['diperoleh']!r}")

    out = Path(__file__).resolve().parent / "results"
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "dijalankan_pada": datetime.now().isoformat(timespec="seconds"),
        "model": config.GEMINI_MODEL,
        "temperature": config.DIALOGUE_TEMPERATURE,
        "seed": config.GENERATION_SEED,
        "ringkasan": r,
        "hasil": [asdict(h) for h in hasil],
    }
    path = out / "dialogue_eval_results.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\nHasil lengkap: {path}")


if __name__ == "__main__":
    main()
