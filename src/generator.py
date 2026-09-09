"""Wrapper Gemini API untuk dialogue analyzer, plan generator, dan compliance checker."""

from __future__ import annotations
import json
import random
import time

from src.config import config, ARM_DESIGN

TRANSIENT_MARKERS = (
    "503", "500", "502", "504", "429",
    "unavailable", "high demand", "overloaded",
    "resource_exhausted", "deadline_exceeded", "rate limit",
    "timeout", "timed out", "connection", "temporarily",
)

PERMANENT_MARKERS = (
    "api key", "api_key_invalid", "permission_denied", "unauthenticated",
    "invalid_argument", "not found", "404", "401", "403",
)


def is_transient_error(exc: Exception) -> bool:
    """True jika galat berpeluang hilang dengan mencoba ulang."""
    message = f"{type(exc).__name__} {exc}".lower()
    if any(marker in message for marker in PERMANENT_MARKERS):
        return False
    return any(marker in message for marker in TRANSIENT_MARKERS)


def _backoff_delay(attempt: int) -> float:
    """Jeda yang menggandakan diri, diberi acakan agar tidak serempak."""
    delay = config.RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
    return min(delay, config.RETRY_MAX_DELAY_SECONDS) * random.uniform(0.8, 1.2)


def _get_client():
    from google import genai

    if not config.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY belum diset. Isi di file .env (lihat .env.example) "
            "dengan key dari https://aistudio.google.com/apikey"
        )
    return genai.Client(api_key=config.GEMINI_API_KEY)


def _generation_config(temperature: float, *, json_mode: bool = False):
    from google.genai import types

    options = {"temperature": temperature}
    if config.GENERATION_SEED is not None:
        options["seed"] = config.GENERATION_SEED
    if json_mode:
        options["response_mime_type"] = "application/json"
    return types.GenerateContentConfig(**options)


def _extract_text(response, *, context: str) -> str:
    """Ambil teks respons, atau lempar galat yang menyebutkan finish_reason."""
    text = getattr(response, "text", None)
    if text and text.strip():
        return text

    reason = "tidak diketahui"
    try:
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            reason = str(getattr(candidates[0], "finish_reason", reason))
        feedback = getattr(response, "prompt_feedback", None)
        if feedback is not None:
            reason = f"{reason}; prompt_feedback={feedback}"
    except Exception:
        pass

    raise RuntimeError(
        f"[{context}] Gemini mengembalikan respons kosong (temporarily). "
        f"Kemungkinan penyebab: {reason}"
    )


def _parse_json_response(raw_text: str, *, context: str) -> dict:
    """Uraikan JSON, dengan satu upaya perbaikan otomatis bila sintaksnya rusak."""
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    from json_repair import repair_json

    repaired = repair_json(raw_text, return_objects=True)
    if isinstance(repaired, dict):
        return repaired

    raise ValueError(
        f"[{context}] Respons Gemini bukan JSON object yang valid, bahkan setelah "
        f"dicoba diperbaiki (temporarily).\nRaw response:\n{raw_text[:400]}"
    )


def _call_with_retry(call, *, context: str):
    """Jalankan call(model) dengan percobaan ulang dan model cadangan."""
    models = [config.GEMINI_MODEL]
    if config.GEMINI_FALLBACK_MODEL:
        models.append(config.GEMINI_FALLBACK_MODEL)

    last_error: Exception | None = None

    for model_index, model in enumerate(models):
        if model_index > 0:
            print(f"    [info] beralih ke model cadangan: {model}")

        for attempt in range(1, config.RETRY_MAX_ATTEMPTS + 1):
            try:
                return call(model)
            except Exception as e:
                last_error = e

                if not is_transient_error(e):
                    raise RuntimeError(
                        f"[{context}] Galat yang tidak bisa diperbaiki dengan "
                        f"mencoba ulang: {e}"
                    ) from e

                if attempt == config.RETRY_MAX_ATTEMPTS:
                    break

                delay = _backoff_delay(attempt)
                print(
                    f"    [retry] {context}: {type(e).__name__} pada percobaan "
                    f"{attempt}/{config.RETRY_MAX_ATTEMPTS}, "
                    f"menunggu {delay:.1f} detik..."
                )
                time.sleep(delay)

    scope = f" pada {len(models)} model" if len(models) > 1 else ""
    raise RuntimeError(
        f"[{context}] Server model bahasa masih sibuk setelah "
        f"{config.RETRY_MAX_ATTEMPTS} percobaan{scope}. Ini gangguan sementara di "
        f"sisi penyedia, bukan kesalahan masukan. Coba lagi beberapa saat lagi.\n"
        f"Galat terakhir: {last_error}"
    )


def _generate_text(prompt: str, *, context: str, temperature: float) -> str:
    client = _get_client()

    def call(model: str) -> str:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=_generation_config(temperature),
        )
        return _extract_text(response, context=context)

    return _call_with_retry(call, context=context)


def _generate_json(prompt: str, *, context: str, temperature: float) -> dict:
    client = _get_client()

    def call(model: str) -> dict:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=_generation_config(temperature, json_mode=True),
        )
        raw = _extract_text(response, context=context)
        return _parse_json_response(raw, context=context)

    return _call_with_retry(call, context=context)


DIALOGUE_ANALYZER_PROMPT = """Kamu adalah asisten yang menganalisis SATU pesan pengguna aplikasi kebugaran.
Pesan ini bisa jadi pesan pembuka, atau balasan singkat atas pertanyaan lanjutan
dari sistem (misal user cuma jawab "5x seminggu" tanpa konteks lain). Ekstrak
APA ADANYA dari pesan ini saja -- JANGAN menebak atau mengarang nilai yang
tidak disebutkan secara eksplisit di pesan ini (biar sistem tau bagian mana
yang masih perlu ditanyakan ke user).

RIWAYAT CEDERA YANG SUDAH TERCATAT SEBELUM PESAN INI: {current_riwayat_cedera}

Ekstrak informasi berikut dalam format JSON:
- tujuan_latihan (string, contoh: "hipertrofi", "kekuatan", "penurunan berat badan";
  null jika tidak disebutkan di pesan ini)
- frekuensi_tersedia (integer, jumlah hari latihan per minggu; null jika tidak
  disebutkan di pesan ini)
- level_pengalaman (string: "pemula", "menengah", "lanjutan"; "tidak_disebutkan"
  jika tidak disebutkan di pesan ini)
- riwayat_cedera: WAJIB tri-state, jangan disamakan antara "belum dijawab" dan
  "sudah dijawab tapi memang nggak ada". PENTING -- pesan ini bisa jadi
  MENAMBAH cedera baru ATAU MENGOREKSI/MENGGANTI cedera yang sudah tercatat
  (lihat daftar di atas). Baca maksud pesan ini dengan cermat, lalu kembalikan
  DAFTAR LENGKAP riwayat cedera yang seharusnya berlaku SETELAH pesan ini
  (bukan cuma yang baru disebutkan):
    * null              -> pesan ini tidak menyinggung cedera/kondisi fisik
                            sama sekali; daftar lama (di atas) tetap berlaku
                            apa adanya, tidak perlu dikembalikan ulang
    * [] (array kosong) -> user EKSPLISIT bilang tidak ada cedera (mis. "nggak ada",
                            "sehat semua", "aman kok", "gak ada cedera")
    * ["..."]           -> daftar LENGKAP cedera setelah mempertimbangkan pesan
                            ini -- kalau pesan ini menambah cedera baru, GABUNGKAN
                            dengan daftar lama; kalau pesan ini mengoreksi/mengganti
                            salah satu item di daftar lama (mis. "eh salah, kanan
                            bukan kiri", "bukan lutut, maksudnya bahu"), GANTI item
                            yang relevan, jangan duplikat, dan jangan pertahankan
                            item lama yang sudah jelas-jelas dikoreksi
- catatan_tambahan (string, ringkasan singkat hal lain yang relevan di pesan ini;
  string kosong "" jika tidak ada)

Balas HANYA dengan JSON valid, tanpa teks lain, tanpa markdown code fence.

Pesan pengguna: "{user_message}"
"""


def analyze_dialogue(user_message: str, current_riwayat_cedera: list | None = None) -> dict:
    """Ekstrak slot profil dari satu pesan pengguna."""
    if current_riwayat_cedera is None:
        cedera_context = "(belum ada, ini pertanyaan pertama soal cedera)"
    elif current_riwayat_cedera == []:
        cedera_context = "(user sudah bilang tidak ada cedera)"
    else:
        cedera_context = json.dumps(current_riwayat_cedera, ensure_ascii=False)

    prompt = DIALOGUE_ANALYZER_PROMPT.format(
        user_message=user_message,
        current_riwayat_cedera=cedera_context,
    )
    return _generate_json(
        prompt, context="dialogue_analyzer", temperature=config.DIALOGUE_TEMPERATURE
    )


PROMPT_HEADER = """Kamu adalah pelatih kebugaran berpengalaman yang menjelaskan rencana
latihan langsung ke kliennya lewat chat.

PROFIL PENGGUNA:
{user_profile}
"""

CONTEXT_BLOCK = """
KONTEKS ILMIAH:
{context}
"""

TASK_GROUNDED = """
TUGAS:
Susun rencana latihan yang sesuai profil pengguna, dengan aturan:
1. Gunakan HANYA informasi pada konteks ilmiah di atas sebagai dasar rekomendasi,
   jangan menambahkan klaim yang tidak didukung konteks tersebut.
2. Setiap rekomendasi HARUS bisa ditelusuri ke salah satu sumber di atas.
3. Jika pengguna punya riwayat cedera, sebutkan modifikasi atau gerakan yang
   dihindari berdasarkan sumber yang relevan.
4. WAJIB: bubuhkan penanda sumber di akhir setiap kalimat yang memuat
   rekomendasi, memakai format [S1], [S2], dan seterusnya sesuai nomor Sumber
   pada konteks ilmiah di atas. Contoh penulisannya:
   "Dua sesi per minggu sudah memadai untuk pemula [S1]."
   Kalimat sapaan, penutup, atau kalimat yang tidak memuat rekomendasi tidak
   perlu diberi penanda. Jangan membuat daftar sumber terpisah di akhir jawaban,
   sebab penanda di dalam kalimat sudah menggantikannya.
5. Jangan mengarang nomor sumber. Pakai hanya nomor yang benar-benar ada pada
   konteks di atas.
6. Jika konteks yang tersedia tidak cukup untuk menjawab dengan aman, katakan
   dengan jujur bahwa informasi belum mencukupi, jangan mengarang.
7. NAMA GERAKAN: utamakan nama gerakan yang benar-benar muncul pada konteks.
   Kalau konteks hanya membahas pola gerakan secara umum, kamu BOLEH menyebut
   contoh gerakan yang lazim mewakili pola itu, dengan dua syarat. Pertama,
   tuliskan sebagai contoh memakai kata "misalnya". Kedua, JANGAN bubuhkan
   penanda sumber pada bagian contoh tersebut, sebab nama itu bukan berasal
   dari konteks. Contoh penulisannya:
   "Latih pola mendorong untuk tubuh bagian atas, misalnya bench press atau
   push-up, sebanyak 3 sampai 4 set per sesi [S1]."
   Penanda [S1] pada contoh di atas menempel pada anjuran jumlah setnya, bukan
   pada nama gerakannya.
8. ANGKA SET DAN REPETISI: kalau angkanya ada pada konteks, pakai angka itu dan
   beri penanda sumber. Kalau tidak ada, kamu BOLEH menurunkan angka praktis
   dari prinsip yang ada pada konteks, dengan dua syarat. Pertama, hasil
   turunannya tidak boleh melanggar rentang yang disebut konteks. Kedua,
   sebutkan dasar turunannya dalam kalimat yang sama. Contoh penulisannya:
   "Konteks menganjurkan 10 sampai 20 set per kelompok otot tiap minggu [S1],
   sehingga dengan tiga sesi per minggu cukup 3 sampai 4 set per gerakan."
9. BENTUK RENCANA: susun rencana per sesi latihan. Untuk setiap sesi, sebutkan
   nama gerakan, jumlah set, dan rentang repetisi, supaya rencana dapat langsung
   dijalankan pengguna. Jangan berhenti pada prinsip umum saja.
10. Jangan menyebut angka beban dalam kilogram, sebab beban bergantung pada
   kemampuan masing-masing orang. Sampaikan intensitas sebagai persentase dari
   kemampuan maksimal atau sebagai sisa repetisi sebelum gagal, sesuai konteks.
11. JADWAL MINGGUAN: susun rencana sebagai jadwal per hari, sebanyak hari
   latihan yang tersedia pada profil pengguna. Untuk setiap hari latihan,
   sebutkan fokus kelompok ototnya beserta daftar gerakan, jumlah set, dan
   rentang repetisinya. Sebutkan pula hari mana yang dipakai untuk istirahat,
   sehingga pengguna tahu susunan satu minggu penuh.
   Pembagian hari dan penempatan hari istirahat adalah penataan praktis, bukan
   kutipan dari konteks, sehingga JANGAN diberi penanda sumber. Penanda hanya
   dibubuhkan pada prinsip yang mendasarinya. Contoh penulisannya:
   "Hari 1, tubuh bagian bawah: pola menekuk lutut, misalnya squat, 3 sampai 4
    set dengan 5 sampai 8 repetisi."
   "Hari 3 dipakai untuk istirahat."
   "Susunan ini menjaga tiap kelompok otot terlatih minimal dua kali seminggu [S1]."
12. Jangan menjadwalkan kelompok otot yang sama pada dua hari latihan berturut-turut,
   dan selingi hari latihan dengan hari istirahat secara merata sepanjang minggu.
   Kalau konteks menyebut lama istirahat antar-set, sertakan angkanya beserta
   penanda sumber.
"""

TASK_PLAIN = """
TUGAS:
Susun rencana latihan yang sesuai profil pengguna. Jika pengguna punya riwayat
cedera, sebutkan modifikasi atau gerakan yang sebaiknya dihindari.
"""

STYLE_RULES = """
ATURAN GAYA PENULISAN (PENTING, WAJIB DIIKUTI):
- Tulis seperti chat biasa ke klien, pakai paragraf mengalir dan kalimat lengkap,
  BUKAN seperti laporan atau dokumen formal.
- JANGAN pakai heading markdown (tanda #, ##, ###, dst).
- JANGAN pakai bold/italic markdown (tanda ** atau *) untuk menekankan istilah.
  Kalau perlu menonjolkan nama latihan atau angka, cukup tulis apa adanya dalam
  kalimat, tanpa simbol pemformatan.
- JANGAN pakai garis pemisah seperti "---" atau "===".
- Bullet/list HANYA boleh dipakai untuk daftar latihan per sesi (maksimal 1 level,
  pakai tanda "-" biasa), bukan untuk seluruh isi rencana.
- Sapa penggunanya langsung (gaya "kamu"), bukan orang ketiga.
- Jangan ulangi profil pengguna secara verbatim di awal jawaban -- langsung masuk
  ke rencananya, seolah kamu sudah paham situasinya.
- JANGAN membuka jawaban dengan sapaan atau basa-basi seperti "Halo", "Senang
  sekali bisa membantu", atau "Baik, mari kita mulai". Langsung ke isi rencananya
  pada kalimat pertama.
- JANGAN menutup jawaban dengan kalimat penyemangat seperti "Selamat berlatih",
  "Semangat ya", atau "Semoga berhasil". Akhiri pada kalimat terakhir yang masih
  berisi informasi.
"""


def build_plan_prompt(
    user_profile: dict,
    context: str | None,
    *,
    use_context: bool,
    use_grounding_instructions: bool,
) -> str:
    """Susun prompt plan generator untuk satu lengan evaluasi."""
    if use_context and not context:
        raise ValueError(
            "Lengan ini menuntut konteks, tetapi konteks yang diberikan kosong."
        )

    sections = [
        PROMPT_HEADER.format(
            user_profile=json.dumps(user_profile, ensure_ascii=False, indent=2)
        )
    ]
    if use_context:
        sections.append(CONTEXT_BLOCK.format(context=context))
    sections.append(TASK_GROUNDED if use_grounding_instructions else TASK_PLAIN)
    sections.append(STYLE_RULES)
    return "".join(sections)


def generate_plan_for_arm(
    user_profile: dict,
    context: str | None = None,
    *,
    arm: str = "rag",
) -> str:
    """Hasilkan rencana latihan untuk satu lengan evaluasi."""
    if arm not in ARM_DESIGN:
        raise ValueError(f"Lengan tidak dikenal: {arm}. Pilihan: {list(ARM_DESIGN)}")

    use_context, use_grounding = ARM_DESIGN[arm]
    prompt = build_plan_prompt(
        user_profile,
        context,
        use_context=use_context,
        use_grounding_instructions=use_grounding,
    )
    return _generate_text(
        prompt,
        context=f"plan_generator[{arm}]",
        temperature=config.GENERATION_TEMPERATURE,
    )


def generate_plan(user_profile: dict, context: str) -> str:
    """Jalur RAG utama yang dipakai pipeline produksi."""
    return generate_plan_for_arm(user_profile, context, arm="rag")


def generate_plan_baseline_non_rag(user_profile: dict) -> str:
    """Lengan pembanding tanpa retrieval."""
    return generate_plan_for_arm(user_profile, None, arm="baseline")


REVISION_PROMPT = """Rencana latihan berikut MELANGGAR batasan keselamatan pengguna
dan harus kamu susun ulang.

PROFIL PENGGUNA:
{user_profile}

KONTEKS ILMIAH:
{context}

RENCANA SEBELUMNYA:
{plan}

PELANGGARAN YANG DITEMUKAN:
{violations}

TUGAS:
Susun ulang rencana tersebut sehingga seluruh pelanggaran di atas hilang.
Ganti gerakan yang bermasalah dengan alternatif yang aman menurut konteks
ilmiah, jangan sekadar menghapusnya tanpa pengganti. Pertahankan bagian
rencana yang sudah aman. Aturan penanda sumber dan aturan gaya penulisan yang
berlaku sebelumnya tetap harus diikuti.
"""


def regenerate_plan_with_feedback(
    user_profile: dict,
    context: str,
    previous_plan: str,
    violations: list[str],
) -> str:
    """Susun ulang rencana yang melanggar batasan, dengan pelanggaran sebagai umpan balik."""
    prompt = REVISION_PROMPT.format(
        user_profile=json.dumps(user_profile, ensure_ascii=False, indent=2),
        context=context,
        plan=previous_plan,
        violations="\n".join(f"- {v}" for v in violations) or "- (tidak dirinci)",
    ) + STYLE_RULES
    return _generate_text(
        prompt,
        context="plan_generator[revisi]",
        temperature=config.GENERATION_TEMPERATURE,
    )


FOLLOWUP_PROMPT = """Kamu adalah pelatih kebugaran yang sedang menjawab pertanyaan
lanjutan dari klien mengenai rencana latihan yang baru saja kamu susun untuknya.

PROFIL PENGGUNA:
{user_profile}

KONTEKS ILMIAH:
{context}

RENCANA YANG SUDAH KAMU BERIKAN:
{plan}

PERTANYAAN KLIEN:
{question}

TUGAS:
Jawab pertanyaan itu dengan aturan:
1. Gunakan konteks ilmiah di atas dan rencana yang sudah kamu berikan sebagai
   dasar jawaban.
2. Bubuhkan penanda sumber [S1], [S2], dan seterusnya di akhir kalimat yang
   memuat klaim berdasarkan konteks, sesuai nomor Sumber di atas.
3. Jika pertanyaannya di luar cakupan latihan beban, misalnya soal gizi, obat,
   diagnosis medis, atau cabang olahraga lain, katakan terus terang bahwa hal itu
   di luar cakupan sistem ini dan sarankan berkonsultasi dengan tenaga yang tepat.
   Jangan mengarang jawaban.
4. Jika konteks tidak memuat jawabannya, katakan dengan jujur bahwa informasinya
   tidak tersedia pada dokumen yang kamu pakai.
5. Jawab ringkas, cukup satu sampai tiga paragraf pendek. Jangan mengulang
   seluruh rencana.
"""


def answer_followup(
    user_profile: dict,
    context: str,
    plan: str,
    question: str,
) -> str:
    """Jawab pertanyaan lanjutan memakai konteks yang sama, tanpa retrieval ulang."""
    prompt = FOLLOWUP_PROMPT.format(
        user_profile=json.dumps(user_profile, ensure_ascii=False, indent=2),
        context=context,
        plan=plan,
        question=question,
    ) + STYLE_RULES
    return _generate_text(
        prompt,
        context="followup",
        temperature=config.GENERATION_TEMPERATURE,
    )


COMPLIANCE_CHECK_PROMPT = """Periksa apakah RENCANA LATIHAN di bawah ini melanggar
CONSTRAINT pengguna (misal: menyarankan exercise yang seharusnya dihindari
karena riwayat cedera).

CONSTRAINT PENGGUNA:
{constraints}

RENCANA LATIHAN:
{plan}

Balas dalam format JSON:
{{
  "patuh": true/false,
  "pelanggaran": ["daftar pelanggaran spesifik jika ada, kosongkan jika patuh"]
}}
Balas HANYA JSON, tanpa teks lain.
"""


def check_compliance(plan: str, constraints: dict) -> dict:
    """Periksa rencana terhadap constraint riwayat cedera pengguna."""
    prompt = COMPLIANCE_CHECK_PROMPT.format(
        constraints=json.dumps(constraints, ensure_ascii=False, indent=2),
        plan=plan,
    )
    return _generate_json(
        prompt, context="compliance_checker", temperature=config.COMPLIANCE_TEMPERATURE
    )
