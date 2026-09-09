"""Evaluasi RAGAs antar-lengan dengan metrik Faithfulness dan ResponseGroundedness.

Rancangan lengan dijelaskan pada src/config.py bagian EVAL_ARMS.
"""

from __future__ import annotations
import asyncio
import csv
import json
import math
import statistics
import sys
import types
from dataclasses import dataclass, field, asdict
from datetime import datetime
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import langchain_community.chat_models.vertexai
except ModuleNotFoundError:
    try:
        from langchain_google_vertexai import ChatVertexAI as _ChatVertexAI
    except ModuleNotFoundError:
        class _ChatVertexAI:
            def __init__(self, *args, **kwargs):
                raise RuntimeError(
                    "ChatVertexAI stub -- project ini nggak pakai VertexAI sama sekali."
                )

    _shim = types.ModuleType("langchain_community.chat_models.vertexai")
    _shim.ChatVertexAI = _ChatVertexAI
    sys.modules["langchain_community.chat_models.vertexai"] = _shim


from src.config import config, validate_config, ARM_DESIGN
from src.pipeline import TrainingPlanPipeline
from src.generator import generate_plan_for_arm
from src.citations import strip_source_markers
from src.retriever import (
    format_full_documents_for_prompt,
    collect_evaluation_contexts,
)
from evaluation.scenarios import SCENARIOS

from ragas.llms import LangchainLLMWrapper
from ragas.dataset_schema import SingleTurnSample
from ragas.metrics import Faithfulness, ResponseGroundedness
from langchain_google_genai import ChatGoogleGenerativeAI


def is_valid_score(value) -> bool:
    """True hanya untuk angka yang layak masuk rata-rata, menyaring None dan NaN."""
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return True


def reconstruct_claim_ratio(score, max_denominator: int = 60) -> str | None:
    """Perkirakan pecahan 'klaim didukung / total klaim' dari skor desimal."""
    if not is_valid_score(score) or score == 0:
        return None
    f = Fraction(float(score)).limit_denominator(max_denominator)
    return f"{f.numerator}/{f.denominator}"


@dataclass
class ArmResult:
    arm: str
    plan: str
    faithfulness: float | None
    groundedness: float | None
    claims: str | None = None


@dataclass
class ScenarioResult:
    scenario_id: str
    message: str
    extracted_profile: dict
    retrieved_sources: list[str]
    context_mode: str
    n_context_items: int
    context_chars: int
    arms: dict = field(default_factory=dict)


def build_evaluator_llm():
    """Bangun model penilai, terpisah dari model penyusun bila diatur demikian."""
    if not config.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY belum diset -- isi dulu di .env sebelum jalanin evaluasi."
        )

    judge_model = config.EVAL_JUDGE_MODEL or config.GEMINI_MODEL
    if judge_model == config.GEMINI_MODEL:
        print(
            f"Peringatan: model penilai sama dengan model penyusun "
            f"({judge_model}). Hasilnya berupa evaluasi diri, sehingga skor "
            f"berpotensi bias. Set EVAL_JUDGE_MODEL untuk memisahkannya."
        )
    else:
        print(f"Model penilai: {judge_model} (penyusun: {config.GEMINI_MODEL})")

    llm = ChatGoogleGenerativeAI(
        model=judge_model,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0.0,
    )
    return LangchainLLMWrapper(llm)


async def score_one(
    evaluator_llm, question: str, response: str, contexts: list[str]
) -> tuple[float | None, float | None]:
    if not response or not response.strip() or not contexts:
        return None, None

    sample = SingleTurnSample(
        user_input=question,
        response=response,
        retrieved_contexts=contexts,
    )

    faithfulness_scorer = Faithfulness(llm=evaluator_llm)
    groundedness_scorer = ResponseGroundedness(llm=evaluator_llm)

    try:
        faithfulness_score = await faithfulness_scorer.single_turn_ascore(sample)
    except Exception as e:
        print(f"    [warn] gagal hitung faithfulness: {e}")
        faithfulness_score = None

    await asyncio.sleep(config.API_PACING_DELAY_SECONDS)

    try:
        groundedness_score = await groundedness_scorer.single_turn_ascore(sample)
    except Exception as e:
        print(f"    [warn] gagal hitung groundedness: {e}")
        groundedness_score = None

    return faithfulness_score, groundedness_score


def run_until_plan(pipeline, message: str, max_turns: int = 3):
    """Jalankan pipeline sampai rencana tersusun.

    Sejak tahap konfirmasi ditambahkan, profil yang lengkap tidak langsung
    menghasilkan rencana melainkan meminta pengguna memastikan ringkasannya.
    Evaluasi menirukan pemastian itu dengan mengirim jawaban pembenaran, yang
    ditangani secara deterministik tanpa memanggil model bahasa.
    """
    result = pipeline.run(message)
    turns = 1

    while result.status == "butuh_konfirmasi" and turns < max_turns:
        result = pipeline.run("ya")
        turns += 1

    return result


async def run_scenario(pipeline, evaluator_llm, scenario: dict) -> ScenarioResult | None:
    scenario_id = scenario["id"]
    message = scenario["message"]
    print(f"\n[{scenario_id}] {message[:70]}...")

    pipeline.reset()
    result = run_until_plan(pipeline, message)

    if result is None or result.status != "rencana_siap":
        status = result.status if result else "tidak ada hasil"
        print(
            f"    [warn] skenario ini tidak sampai ke tahap rencana "
            f"(status terakhir={status}). Cek ulang kalimat skenario di "
            f"scenarios.py."
        )
        return None

    profile = result.extracted_profile
    documents = result.retrieved_documents
    sources = result.retrieved_sources

    generation_context = format_full_documents_for_prompt(documents)
    eval_contexts = collect_evaluation_contexts(documents)
    context_chars = sum(len(c) for c in eval_contexts)

    print(f"    sumber: {sources}")
    print(
        f"    konteks penilaian: {len(eval_contexts)} item, "
        f"{context_chars:,} karakter (mode {config.EVAL_CONTEXT_MODE})"
    )

    question = (
        f"Susun rencana latihan untuk profil: "
        f"{json.dumps(profile, ensure_ascii=False)}"
    )

    arms: dict[str, dict] = {}
    for arm in config.EVAL_ARMS:
        use_context, _ = ARM_DESIGN[arm]

        await asyncio.sleep(config.API_PACING_DELAY_SECONDS)

        if arm == "rag":
            plan = result.plan
        else:
            plan = generate_plan_for_arm(
                profile,
                generation_context if use_context else None,
                arm=arm,
            )

        scored_plan = strip_source_markers(plan)
        faith, ground = await score_one(
            evaluator_llm, question, scored_plan, eval_contexts
        )
        print(f"    {arm:<16} faithfulness={faith}  groundedness={ground}")

        arms[arm] = asdict(ArmResult(
            arm=arm,
            plan=plan,
            faithfulness=faith,
            groundedness=ground,
            claims=reconstruct_claim_ratio(faith),
        ))

    return ScenarioResult(
        scenario_id=scenario_id,
        message=message,
        extracted_profile=profile,
        retrieved_sources=sources,
        context_mode=config.EVAL_CONTEXT_MODE,
        n_context_items=len(eval_contexts),
        context_chars=context_chars,
        arms=arms,
    )


def mean_of(values: list) -> tuple[float | None, int]:
    clean = [v for v in values if is_valid_score(v)]
    if not clean:
        return None, 0
    return round(statistics.mean(clean), 4), len(clean)


def summarize(results: list[ScenarioResult], failed: list[str]) -> None:
    print("\nRINGKASAN HASIL EVALUASI")
    print(f"Mode konteks penilaian : {config.EVAL_CONTEXT_MODE}")
    print(f"Model penilai          : {config.EVAL_JUDGE_MODEL or config.GEMINI_MODEL}")
    print(f"Seed generasi          : {config.GENERATION_SEED}")
    print(f"Temperature generasi   : {config.GENERATION_TEMPERATURE}")

    print(f"\n{'Lengan':<18}{'Konteks':>9}{'Instruksi':>11}"
          f"{'Faith':>9}{'(n)':>6}{'Ground':>9}{'(n)':>6}")
    for arm in config.EVAL_ARMS:
        use_context, use_instruction = ARM_DESIGN[arm]
        f, nf = mean_of([r.arms[arm]["faithfulness"] for r in results if arm in r.arms])
        g, ng = mean_of([r.arms[arm]["groundedness"] for r in results if arm in r.arms])
        print(
            f"{arm:<18}{'ya' if use_context else 'tidak':>9}"
            f"{'ya' if use_instruction else 'tidak':>11}"
            f"{str(f):>9}{nf:>6}{str(g):>9}{ng:>6}"
        )

    def rata(arm, metrik):
        if arm not in config.EVAL_ARMS:
            return None
        v, _ = mean_of([r.arms[arm][metrik] for r in results if arm in r.arms])
        return v

    rag_f, base_f, ctx_f = (rata(a, "faithfulness")
                            for a in ("rag", "baseline", "context_only"))
    if None not in (rag_f, base_f):
        print(f"\nSelisih total (rag - baseline)          : {rag_f - base_f:+.4f}")
    if None not in (rag_f, ctx_f):
        print(f"  bagian dari instruksi (rag - context_only): {rag_f - ctx_f:+.4f}")
    if None not in (ctx_f, base_f):
        print(f"  bagian dari konteks (context_only - baseline): {ctx_f - base_f:+.4f}")

    print(f"\nSkenario dijalankan: {len(results)}/{len(SCENARIOS)}")
    if failed:
        print(f"Skenario gagal total: {', '.join(failed)}")

    for arm in config.EVAL_ARMS:
        for label, key in (("Faithfulness", "faithfulness"),
                           ("Groundedness", "groundedness")):
            nan_ids = [
                r.scenario_id for r in results
                if arm in r.arms and not is_valid_score(r.arms[arm][key])
            ]
            if nan_ids:
                print(f"{arm} {label} tidak terhitung pada: {', '.join(nan_ids)}")


def save_results(results: list[ScenarioResult], failed: list[str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "dijalankan_pada": datetime.now().isoformat(timespec="seconds"),
        "konfigurasi": {
            "model": config.GEMINI_MODEL,
            "model_penilai": config.EVAL_JUDGE_MODEL or config.GEMINI_MODEL,
            "lengan": list(config.EVAL_ARMS),
            "mode_konteks": config.EVAL_CONTEXT_MODE,
            "chunk_per_dokumen": config.EVAL_CHUNKS_PER_DOCUMENT,
            "seed": config.GENERATION_SEED,
            "temperature_generasi": config.GENERATION_TEMPERATURE,
        },
        "skenario_gagal": failed,
        "jumlah_skenario_total": len(SCENARIOS),
        "hasil": [asdict(r) for r in results],
    }

    json_path = out_dir / "ragas_eval_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    csv_path = out_dir / "ragas_eval_summary.csv"
    header = ["scenario_id", "mode_konteks", "n_item_konteks", "karakter_konteks"]
    for arm in config.EVAL_ARMS:
        header += [f"{arm}_faithfulness", f"{arm}_klaim", f"{arm}_groundedness"]
    header.append("sumber_yang_diambil")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for r in results:
            row = [r.scenario_id, r.context_mode, r.n_context_items, r.context_chars]
            for arm in config.EVAL_ARMS:
                a = r.arms.get(arm, {})
                row += [a.get("faithfulness"), a.get("claims") or "",
                        a.get("groundedness")]
            row.append("; ".join(r.retrieved_sources))
            writer.writerow(row)

    print(f"\nHasil lengkap (termasuk teks plan): {json_path}")
    print(f"Ringkasan buat lampiran skripsi (CSV/Excel): {csv_path}")


async def run_scenario_with_retry(
    pipeline, evaluator_llm, scenario: dict,
    max_retries: int = 2, retry_delay_seconds: int = 15,
) -> ScenarioResult | None:
    for attempt in range(1, max_retries + 2):
        try:
            return await run_scenario(pipeline, evaluator_llm, scenario)
        except Exception as e:
            is_last = attempt == max_retries + 1
            print(f"    [error] percobaan {attempt} gagal: {e}")
            if is_last:
                print(f"    [SKIP] {scenario['id']} dilewati setelah {attempt} percobaan.")
                return None
            print(f"    [retry] nunggu {retry_delay_seconds} detik sebelum coba lagi...")
            await asyncio.sleep(retry_delay_seconds)
    return None


async def main() -> None:
    for w in validate_config():
        print(f"Peringatan: {w}")

    evaluator_llm = build_evaluator_llm()
    pipeline = TrainingPlanPipeline()
    out_dir = Path(__file__).resolve().parent / "results"

    results: list[ScenarioResult] = []
    failed: list[str] = []

    print(f"Lengan yang dijalankan: {', '.join(config.EVAL_ARMS)}")

    scenarios = SCENARIOS
    if config.EVAL_SCENARIO_LIMIT:
        scenarios = SCENARIOS[: config.EVAL_SCENARIO_LIMIT]
        print(
            f"Uji cepat: hanya {len(scenarios)} skenario pertama dari "
            f"{len(SCENARIOS)} yang dijalankan. Set EVAL_SCENARIO_LIMIT ke None "
            f"untuk menjalankan seluruhnya."
        )

    for scenario in scenarios:
        r = await run_scenario_with_retry(pipeline, evaluator_llm, scenario)
        if r is None:
            failed.append(scenario["id"])
        else:
            results.append(r)
        save_results(results, failed, out_dir)
        await asyncio.sleep(config.API_PACING_DELAY_SECONDS)

    summarize(results, failed)
    save_results(results, failed, out_dir)


if __name__ == "__main__":
    asyncio.run(main())
