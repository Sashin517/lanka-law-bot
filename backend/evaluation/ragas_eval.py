"""RAGAS evaluation for LankaLawBot — industry-standard RAG quality metrics.

Evaluates the end-to-end LangGraph pipeline on a stratified subset of 20 QA
pairs (4 per mode: quick_qa, deep_research, drafting, review, reasoning),
measuring Faithfulness, FactualCorrectness, and LLMContextRecall.

The script respects Gemini free-tier rate limits (15 RPM for
gemini-3.1-flash-lite) by enforcing sequential execution with
calibrated inter-call delays.

Workflow
--------
1. **Select**: Stratified sample of 4 entries per mode (20 total).
2. **Collect**: Run each through the LangGraph pipeline, capturing
   retrieved_contexts from ``AgentState.retrieved_sources``.
3. **Cache**: Save raw (question, response, contexts, reference) to disk
   so evaluation can be re-run without re-collecting.
4. **Evaluate**: Run RAGAS metrics with ``max_workers=1`` and 4s delays
   to stay within 15 RPM.

Usage
-----
  # Full run (collect + evaluate):
  python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json

  # Collect only (save to cache for later evaluation):
  python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json --collect-only

  # Evaluate from cache (no pipeline calls):
  python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json --cached
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BACKEND_DIR / "benchmarks" / "results" / "_ragas_cache"

# ── Configuration ────────────────────────────────────────────────

# Stratified selection: 4 per mode × 5 modes = 20 total
SAMPLES_PER_MODE = 4
TARGET_MODES = ["quick_qa", "deep_research", "drafting", "review", "reasoning"]

# Gemini free-tier: 15 RPM for gemini-3.1-flash-lite
# Pipeline makes ~1-2 LLM calls per sample during collection.
# RAGAS makes ~5-8 LLM calls per sample during evaluation.
# 4s between calls → max ~15 calls/min → safe for 15 RPM.
COLLECTION_DELAY_S = 5  # Between pipeline calls during collection
EVAL_DELAY_S = 4  # Between RAGAS evaluator calls (via RunConfig)


# ── Stratified selection ─────────────────────────────────────────


def select_stratified_subset(
    benchmark: list[dict],
    per_mode: int = SAMPLES_PER_MODE,
    modes: list[str] = TARGET_MODES,
) -> list[dict]:
    """Select a balanced subset: ``per_mode`` entries from each mode.

    Selection priority:
    1. Skip clarification category (they produce no substantive answer).
    2. Skip entries requiring user documents with placeholder IDs.
    3. Prefer entries with difficulty spread (easy → medium → hard).
    """
    by_mode: dict[str, list[dict]] = defaultdict(list)
    for entry in benchmark:
        mode = entry.get("mode", "quick_qa")
        category = entry.get("category", "")

        # Skip clarification — no evaluable answer
        if category == "clarification":
            continue

        # Skip entries with placeholder doc IDs
        doc_ids = entry.get("request", {}).get("document_ids", [])
        real_docs = [d for d in doc_ids if d and not d.startswith("<")]
        if entry.get("requires_user_document") and not real_docs:
            continue

        if mode in modes:
            by_mode[mode].append(entry)

    # Sort each mode by difficulty for diversity: easy → medium → hard
    difficulty_order = {"easy": 0, "medium": 1, "hard": 2}
    selected: list[dict] = []

    for mode in modes:
        candidates = by_mode.get(mode, [])
        candidates.sort(
            key=lambda e: difficulty_order.get(e.get("difficulty", "medium"), 1)
        )
        chosen = candidates[:per_mode]

        if len(chosen) < per_mode:
            logger.warning(
                "Mode '%s': only %d/%d entries available", mode, len(chosen), per_mode
            )

        selected.extend(chosen)
        logger.info(
            "Mode %-15s → %d entries selected (of %d available)",
            mode,
            len(chosen),
            len(candidates),
        )

    logger.info("Total stratified subset: %d entries", len(selected))
    return selected


# ── Collection phase ─────────────────────────────────────────────


async def collect_samples(entries: list[dict]) -> list[dict]:
    """Run each entry through the LangGraph pipeline, capturing retrieval context.

    Returns serializable dicts suitable for caching and later RAGAS evaluation.
    """
    from evaluation.eval_pipeline import run_pipeline

    samples: list[dict] = []

    for i, item in enumerate(entries):
        question = item["question"]
        mode = item.get("mode", "quick_qa")
        doc_ids = item.get("request", {}).get("document_ids", [])
        doc_ids = [d for d in doc_ids if d and not d.startswith("<")]
        matter_id = item.get("request", {}).get("matter_id")

        logger.info(
            "[%d/%d] Collecting: %s (mode=%s)", i + 1, len(entries), item["id"], mode
        )

        # Rate-limit: wait between pipeline calls (each uses ~1-2 LLM calls)
        if i > 0:
            await asyncio.sleep(COLLECTION_DELAY_S)

        try:
            final_state = await run_pipeline(
                question=question,
                mode=mode,
                document_ids=doc_ids,
                matter_id=matter_id,
            )

            # ── Extract retrieved contexts ──
            # Worker nodes populate state.retrieved_sources with SourceChunk objects
            retrieved_sources = final_state.get("retrieved_sources", [])
            retrieved_contexts: list[str] = []
            for src in retrieved_sources:
                if hasattr(src, "content"):
                    text = src.content or src.excerpt or ""
                elif isinstance(src, dict):
                    text = src.get("content", "") or src.get("excerpt", "")
                else:
                    text = str(src)
                if text.strip():
                    retrieved_contexts.append(text.strip())

            if not retrieved_contexts:
                logger.warning("  → No contexts retrieved, skipping %s", item["id"])
                continue

            # ── Extract response text ──
            # Prefer markdown_content → summary → final_response.answer
            response_text = final_state.get("markdown_content", "") or final_state.get(
                "summary", ""
            )
            if not response_text:
                fr = final_state.get("final_response")
                if isinstance(fr, dict):
                    response_text = fr.get("answer", "")

            if not response_text or "temporarily unavailable" in response_text.lower():
                logger.warning("  → Empty/error response, skipping %s", item["id"])
                continue

            samples.append(
                {
                    "id": item["id"],
                    "mode": mode,
                    "category": item.get("category", ""),
                    "user_input": question,
                    "retrieved_contexts": retrieved_contexts,
                    "response": response_text,
                    "reference": item["ground_truth_answer"],
                }
            )
            logger.info(
                "  ✓ Collected (%d contexts, %d char response)",
                len(retrieved_contexts),
                len(response_text),
            )

        except Exception as e:
            logger.error("  ✗ Failed %s: %s", item["id"], e)
            continue

    return samples


# ── Cache management ─────────────────────────────────────────────


def save_cache(samples: list[dict], cache_path: Path) -> None:
    """Persist collected samples to disk."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(samples, f, indent=2, ensure_ascii=False)
    logger.info("Cached %d samples → %s", len(samples), cache_path)


def load_cache(cache_path: Path) -> list[dict]:
    """Load previously cached samples."""
    with open(cache_path, encoding="utf-8") as f:
        return json.load(f)


# ── RAGAS evaluation ─────────────────────────────────────────────


def run_ragas_evaluation(sample_dicts: list[dict], output_path: Path) -> None:
    """Run RAGAS metrics on collected samples.

    Metrics (3 core):
    - **Faithfulness**: Is the response grounded in retrieved contexts?
      (~3-5 LLM calls/sample: decomposes answer → verifies each claim)
    - **FactualCorrectness**: Does the response match the ground truth?
      (~1-2 LLM calls/sample)
    - **LLMContextRecall**: Did the retriever fetch the right information?
      (~1 LLM call/sample)

    Total budget: 20 samples × ~8 calls = ~160 LLM calls.
    At 15 RPM with 4s spacing → ~11 minutes total.
    """
    from ragas import evaluate, EvaluationDataset, SingleTurnSample
    from ragas.metrics import (
        Faithfulness,
        FactualCorrectness,
        LLMContextRecall,
    )
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.run_config import RunConfig
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_huggingface import HuggingFaceEmbeddings

    # Convert to RAGAS SingleTurnSample objects
    samples = [
        SingleTurnSample(
            user_input=s["user_input"],
            retrieved_contexts=s["retrieved_contexts"],
            response=s["response"],
            reference=s["reference"],
        )
        for s in sample_dicts
    ]

    # ── Evaluator LLM (same model as pipeline, temperature=0 for reproducibility)
    evaluator_llm = LangchainLLMWrapper(
        ChatGoogleGenerativeAI(
            model="gemini-3.1-flash-lite",
            temperature=0,
            google_api_key=os.environ.get("GOOGLE_API_KEY"),
        )
    )

    # ── Embeddings (local — no API calls, no rate limits)
    evaluator_embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    )

    metrics = [
        Faithfulness(),
        FactualCorrectness(),
        LLMContextRecall(),
    ]

    # ── Rate-limit enforcement ──
    # max_workers=1: strictly sequential LLM calls (no concurrent requests)
    # max_retries=30: generous retries for transient 429s
    # max_wait=180: wait up to 3 min before giving up on a single retry
    # timeout=300: 5 min timeout per individual RAGAS sub-call
    run_config = RunConfig(
        max_workers=1,
        max_retries=30,
        max_wait=180,
        timeout=300,
    )

    # Budget estimates
    est_calls = len(samples) * 8  # ~8 LLM calls per sample across 3 metrics
    est_minutes = max(1, est_calls * EVAL_DELAY_S // 60)

    print(f"\n{'='*60}")
    print(f"RAGAS Evaluation")
    print(f"{'='*60}")
    print(f"  Samples:          {len(samples)}")
    print(f"  Metrics:          {', '.join(type(m).__name__ for m in metrics)}")
    print(f"  Est. LLM calls:   ~{est_calls}")
    print(f"  Rate limit:       15 RPM (sequential, max_workers=1)")
    print(f"  Est. duration:    ~{est_minutes} minutes")
    print(f"{'='*60}\n")

    # Print mode distribution in the evaluation set
    mode_counts = defaultdict(int)
    for s in sample_dicts:
        mode_counts[s.get("mode", "unknown")] += 1
    print("  Mode distribution:")
    for mode in TARGET_MODES:
        print(f"    {mode:20s} {mode_counts.get(mode, 0)} samples")
    print()

    # ── Run RAGAS ──
    start_time = time.time()

    results = evaluate(
        dataset=EvaluationDataset(samples=samples),
        metrics=metrics,
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        run_config=run_config,
    )

    elapsed = time.time() - start_time

    # ── Save results ──
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results_df = results.to_pandas()

    # Inject metadata columns
    ids = [s["id"] for s in sample_dicts]
    modes = [s.get("mode", "") for s in sample_dicts]
    categories = [s.get("category", "") for s in sample_dicts]
    results_df.insert(0, "id", ids)
    results_df.insert(1, "mode", modes)
    results_df.insert(2, "category", categories)

    # Compute aggregates (overall + per-mode)
    metric_cols = [
        col
        for col in results_df.columns
        if results_df[col].dtype in ["float64", "float32"]
    ]

    overall_agg = {col: float(results_df[col].mean()) for col in metric_cols}

    per_mode_agg = {}
    for mode in TARGET_MODES:
        mode_df = results_df[results_df["mode"] == mode]
        if not mode_df.empty:
            per_mode_agg[mode] = {
                col: float(mode_df[col].mean()) for col in metric_cols
            }

    results_dict = {
        "aggregate": overall_agg,
        "per_mode_aggregate": per_mode_agg,
        "per_sample": results_df.to_dict(orient="records"),
        "meta": {
            "total_samples": len(samples),
            "samples_per_mode": SAMPLES_PER_MODE,
            "modes": TARGET_MODES,
            "metrics": [type(m).__name__ for m in metrics],
            "model": "gemini-3.1-flash-lite",
            "elapsed_seconds": round(elapsed, 1),
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results_dict, f, indent=2, default=str)

    # ── Print results ──
    print(f"\n{'='*60}")
    print("RAGAS Results — Overall Aggregate")
    print(f"{'='*60}")
    for metric, score in overall_agg.items():
        print(f"  {metric:30s} {score:.4f}")

    print(f"\n{'='*60}")
    print("RAGAS Results — Per Mode")
    print(f"{'='*60}")
    for mode, agg in per_mode_agg.items():
        scores = " | ".join(f"{m}: {s:.3f}" for m, s in agg.items())
        print(f"  {mode:20s} {scores}")

    print(f"\n  Duration:  {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Saved to:  {output_path}")
    print(f"{'='*60}")


# ── CLI ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Run RAGAS evaluation on stratified 20-sample subset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full run (collect + evaluate):
  python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json

  # Phase 1: Collect only (cache pipeline outputs):
  python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json --collect-only

  # Phase 2: Evaluate cached samples:
  python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json --cached

  # Override samples per mode:
  python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json --per-mode 3
        """,
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        required=True,
        help="Path to benchmark JSON (relative to backend/ or absolute)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for results JSON",
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Phase 1: Collect samples and cache (no RAGAS evaluation)",
    )
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Phase 2: Load cached samples, skip collection",
    )
    parser.add_argument(
        "--per-mode",
        type=int,
        default=SAMPLES_PER_MODE,
        help=f"Number of samples per mode (default: {SAMPLES_PER_MODE})",
    )

    args = parser.parse_args()

    # Resolve benchmark path
    benchmark_path = BACKEND_DIR / args.benchmark
    if not benchmark_path.exists():
        benchmark_path = Path(args.benchmark)
    if not benchmark_path.exists():
        print(f"File not found: {args.benchmark}")
        sys.exit(1)

    # Cache path based on benchmark filename + per_mode setting
    cache_name = f"{benchmark_path.stem}_ragas_{args.per_mode}permode.json"
    cache_path = CACHE_DIR / cache_name

    # ── Phase 2: Load from cache ──
    if args.cached:
        if not cache_path.exists():
            print(f"Cache not found: {cache_path}")
            print("Run with --collect-only first to generate the cache.")
            sys.exit(1)
        sample_dicts = load_cache(cache_path)
        print(f"Loaded {len(sample_dicts)} cached samples from {cache_path.name}")

    else:
        # ── Load & select stratified subset ──
        with open(benchmark_path, encoding="utf-8") as f:
            benchmark = json.load(f)
        print(f"Loaded {len(benchmark)} entries from {benchmark_path.name}\n")

        entries = select_stratified_subset(benchmark, per_mode=args.per_mode)
        if not entries:
            print("No valid entries found for evaluation.")
            sys.exit(1)

        # ── Phase 1: Collect ──
        print(f"\nCollecting {len(entries)} samples through LangGraph pipeline...\n")
        sample_dicts = asyncio.run(collect_samples(entries))
        print(f"\nCollected {len(sample_dicts)} valid samples")

        # Always cache after collection
        save_cache(sample_dicts, cache_path)

    # Validate
    if not sample_dicts:
        print("No samples available. Check pipeline and benchmark data.")
        sys.exit(1)

    # ── Phase 1 only: stop here ──
    if args.collect_only:
        print(f"\n✓ Collection complete. {len(sample_dicts)} samples cached.")
        print(f"  Cache: {cache_path}")
        print(f"\nNext step — evaluate:")
        print(
            f"  python -m evaluation.ragas_eval --benchmark {args.benchmark} --cached"
        )
        return

    # ── Run RAGAS evaluation ──
    output_path = (
        Path(args.output)
        if args.output
        else BACKEND_DIR / "benchmarks" / "results" / "ragas_results.json"
    )

    run_ragas_evaluation(sample_dicts, output_path)


if __name__ == "__main__":
    main()
