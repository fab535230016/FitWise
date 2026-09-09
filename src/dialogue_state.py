"""State management untuk percakapan multi-turn (slot-filling)."""

from __future__ import annotations


INITIAL_PROFILE: dict = {
    "tujuan_latihan": None,
    "frekuensi_tersedia": None,
    "level_pengalaman": None,
    "riwayat_cedera": None,
    "catatan_tambahan": "",
}

REQUIRED_FIELDS: list[str] = [
    "tujuan_latihan",
    "frekuensi_tersedia",
    "level_pengalaman",
    "riwayat_cedera",
]

FIELD_LABELS: dict[str, str] = {
    "tujuan_latihan": "Tujuan latihan",
    "frekuensi_tersedia": "Frekuensi per minggu",
    "level_pengalaman": "Level pengalaman",
    "riwayat_cedera": "Riwayat cedera",
}

AFFIRMATIVE_WORDS: frozenset[str] = frozenset({
    "ya", "iya", "yoi", "yup", "yep", "yes", "y",
    "benar", "bener", "betul", "sudah", "udah", "oke", "ok", "okay", "sip",
    "lanjut", "gas", "cocok", "sesuai", "pas", "mantap", "setuju",
})

NEGATIVE_WORDS: frozenset[str] = frozenset({
    "tidak", "nggak", "gak", "ga", "engga", "enggak", "no", "n",
    "belum", "salah", "keliru", "kurang", "bukan", "ralat", "koreksi", "ubah",
})


def _words(message: str) -> list[str]:
    return [w.strip(".,!?;:'\"()") for w in message.lower().split()]


def is_affirmative(message: str) -> bool:
    """True untuk pembenaran singkat seperti 'ya' atau 'sudah benar'."""
    words = [w for w in _words(message) if w]
    if not words or len(words) > 4:
        return False
    if any(w in NEGATIVE_WORDS for w in words):
        return False
    return any(w in AFFIRMATIVE_WORDS for w in words)


def is_negative(message: str) -> bool:
    """True untuk penolakan singkat seperti 'belum' atau 'ada yang salah'."""
    words = [w for w in _words(message) if w]
    if not words or len(words) > 5:
        return False
    return any(w in NEGATIVE_WORDS for w in words)


def format_field(profile: dict, field: str) -> str:
    """Ubah satu nilai profil menjadi teks yang enak dibaca pengguna."""
    value = profile.get(field)
    if field == "riwayat_cedera":
        if value is None:
            return "(belum diisi)"
        if not value:
            return "tidak ada"
        return ", ".join(value)
    if value in (None, "", "tidak_disebutkan"):
        return "(belum diisi)"
    if field == "frekuensi_tersedia":
        return f"{value} hari per minggu"
    return str(value)


def build_profile_summary(profile: dict) -> str:
    """Susun ringkasan profil sebagai daftar berlabel."""
    lines = [f"- {FIELD_LABELS[f]}: {format_field(profile, f)}" for f in REQUIRED_FIELDS]
    note = (profile.get("catatan_tambahan") or "").strip()
    if note:
        lines.append(f"- Catatan tambahan: {note}")
    return "\n".join(lines)


def build_confirmation_question(profile: dict) -> str:
    """Tampilkan ringkasan profil dan minta pengguna memastikannya."""
    return (
        "Sebelum aku susunin rencananya, tolong dicek dulu ya. Ini yang aku "
        "tangkap dari obrolan kita:\n\n"
        f"{build_profile_summary(profile)}\n\n"
        "Sudah benar semua? Kalau sudah, bilang 'ya' atau 'lanjut'. Kalau ada "
        "yang keliru, sebutkan saja bagian mana yang perlu diperbaiki."
    )


FIELD_QUESTIONS: dict[str, str] = {
    "tujuan_latihan": (
        "Tujuan latihannya apa nih? (misalnya nambah otot/hipertrofi, "
        "nurunin berat badan, atau nambah kekuatan)"
    ),
    "frekuensi_tersedia": "Kamu bisa latihan berapa hari dalam seminggu?",
    "level_pengalaman": (
        "Level pengalaman kamu gimana — pemula, menengah, atau udah lanjutan?"
    ),
    "riwayat_cedera": (
        "Ada riwayat cedera atau keluhan fisik tertentu nggak? Ini penting "
        "buat keamanan program latihannya — kalau nggak ada, bilang aja "
        "'nggak ada'."
    ),
}


def merge_profile(base: dict, update: dict) -> dict:
    merged = dict(base)

    for f in ("tujuan_latihan", "frekuensi_tersedia", "level_pengalaman"):
        value = update.get(f)
        if value not in (None, "", "tidak_disebutkan"):
            merged[f] = value

    if update.get("riwayat_cedera") is not None:
        merged["riwayat_cedera"] = update["riwayat_cedera"]

    note = (update.get("catatan_tambahan") or "").strip()
    if note:
        existing = (merged.get("catatan_tambahan") or "").strip()
        merged["catatan_tambahan"] = f"{existing} {note}".strip() if existing else note

    return merged


def get_missing_fields(profile: dict) -> list[str]:
    missing = []
    for f in REQUIRED_FIELDS:
        value = profile.get(f)
        if f == "riwayat_cedera":
            if value is None:
                missing.append(f)
        elif value in (None, "", "tidak_disebutkan"):
            missing.append(f)
    return missing


def _summarize_known(profile: dict) -> str:
    bits = []
    if profile.get("tujuan_latihan"):
        bits.append(f"tujuannya {profile['tujuan_latihan']}")
    if profile.get("frekuensi_tersedia"):
        bits.append(f"{profile['frekuensi_tersedia']}x seminggu")
    level = profile.get("level_pengalaman")
    if level and level != "tidak_disebutkan":
        bits.append(f"level {level}")
    cedera = profile.get("riwayat_cedera")
    if cedera:
        bits.append("ada riwayat cedera: " + ", ".join(cedera))
    elif cedera == []:
        bits.append("nggak ada riwayat cedera")

    if not bits:
        return ""
    return "Oke, catat ya — " + ", ".join(bits) + ". "


def build_clarifying_question(profile: dict, missing_fields: list[str]) -> str:
    intro = _summarize_known(profile)

    if len(missing_fields) == 1:
        return f"{intro}Sebelum aku susunin rencananya — {FIELD_QUESTIONS[missing_fields[0]]}"

    bullet_list = "\n".join(f"- {FIELD_QUESTIONS[f]}" for f in missing_fields)
    return (
        f"{intro}Sebelum aku susunin rencananya, boleh lengkapi dulu:\n\n{bullet_list}"
    )
