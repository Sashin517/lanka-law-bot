"""RAGAS evaluation — captures retrieval context for faithfulness/precision metrics.

Uses the LangGraph pipeline (same path as POST /api/search) and extracts
retrieved_contexts from the final AgentState for RAGAS context-based metrics.

Two-phase workflow for free-tier API compatibility:

  Phase 1 — Collect samples (uses pipeline LLM only):
    python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json --collect-only

  Phase 2 — Evaluate cached samples in batches (uses evaluator LLM only):
    python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json --cached --limit 10
    python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json --cached --limit 10 --offset 10
    ...and so on across multiple days until all samples are scored.

  Single-shot (paid tier):
    python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = BACKEND_DIR / "benchmarks" / "results" / "_ragas_cache"


async def collect_samples(benchmark: list[dict]) -> list[dict]:
    """Run each benchmark entry through the LangGraph pipeline, capturing retrieval context.

    Returns raw dicts (not SingleTurnSample) so they can be JSON-serialized to cache.
    """
    from evaluation.eval_pipeline import run_pipeline

    samples = []

    for i, item in enumerate(benchmark):
        question = item["question"]
        category = item.get("category", "")
        mode = item.get("mode", "quick_qa")
        doc_ids = item.get("request", {}).get("document_ids", [])
        doc_ids = [d for d in doc_ids if d and not d.startswith("<")]
        matter_id = item.get("request", {}).get("matter_id")

        # Skip clarification entries — they produce no substantive answer
        if category == "clarification":
            logger.info(
                "[%d/%d] SKIP (clarification): %s", i + 1, len(benchmark), item["id"]
            )
            continue

        logger.info("[%d/%d] Processing: %s (mode=%s)", i + 1, len(benchmark), item["id"], mode)

        try:
            final_state = await run_pipeline(
                question=question,
                mode=mode,
                document_ids=doc_ids,
                matter_id=matter_id,
            )

            # Extract retrieved contexts from LangGraph state
            retrieved_sources = final_state.get("retrieved_sources", [])
            retrieved_contexts = []
            for src in retrieved_sources:
                # SourceChunk objects or dicts
                if hasattr(src, "content"):
                    text = src.content or src.excerpt
                elif isinstance(src, dict):
                    text = src.get("content", "") or src.get("excerpt", "")
                else:
                    text = str(src)
                if text:
                    retrieved_contexts.append(text)

            if not retrieved_contexts:
                logger.warning("  → No contexts retrieved, skipping")
                continue

            response_text = final_state.get("summary", "")
            if not response_text:
                # Try final_response if available
                fr = final_state.get("final_response", {})
                response_text = fr.get("answer", "") if isinstance(fr, dict) else ""

            if not response_text:
                logger.warning("  → No response generated, skipping")
                continue

            samples.append({
                "id": item["id"],
                "user_input": question,
                "retrieved_contexts": retrieved_contexts,
                "response": response_text,
                "reference": item["ground_truth_answer"],
            })
            logger.info("  ✓ Sample collected (%d contexts)", len(retrieved_contexts))

        except Exception as e:
            logger.error("  ✗ Failed: %s", e)
            continue

    return samples


def save_cache(samples: list[dict], cache_path: Path) -> None:
    """Save collected samples to disk for later evaluation."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(samples, f, indent=2, ensure_ascii=False)
    logger.info("Cached %d samples to %s", len(samples), cache_path)


def load_cache(cache_path: Path) -> list[dict]:
    """Load previously collected samples from disk."""
    with open(cache_path, encoding="utf-8") as f:
        return json.load(f)


def run_ragas_evaluation(
    sample_dicts: list[dict],
    output_path: Path,
    limit: int | None = None,
    offset: int = 0,
) -> None:
    """Run RAGAS evaluation on a slice of cached samples."""
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

    # Slice the samples
    total = len(sample_dicts)
    sliced = sample_dicts[offset:]
    if limit:
        sliced = sliced[:limit]

    if not sliced:
        print(f"No samples in range [offset={offset}, limit={limit}]. Total: {total}")
        sys.exit(1)

    print(f"\nEvaluating samples {offset+1}–{offset+len(sliced)} of {total}")

    # Convert to RAGAS SingleTurnSample objects
    samples = [
        SingleTurnSample(
            user_input=s["user_input"],
            retrieved_contexts=s["retrieved_contexts"],
            response=s["response"],
            reference=s["reference"],
        )
        for s in sliced
    ]

    evaluator_llm = LangchainLLMWrapper(
        ChatGoogleGenerativeAI(
            model="gemini-3.1-flash-lite-preview",
            temperature=0,
            google_api_key=os.environ.get("GOOGLE_API_KEY"),
        )
    )

    evaluator_embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    )

    # 3 core metrics to fit within free-tier daily quota (500 RPD)
    # Faithfulness: ~3-5 LLM calls per sample (decompose + verify claims)
    # FactualCorrectness: ~1-2 LLM calls per sample
    # LLMContextRecall: ~1 LLM call per sample
    # Total: ~5-8 calls per sample → 10 samples ≈ 50-80 calls (safe for 500/day)
    metrics = [
        Faithfulness(),
        FactualCorrectness(),
        LLMContextRecall(),
    ]

    run_config = RunConfig(
        max_workers=1,       # Sequential — critical for free tier (15 RPM)
        max_retries=30,      # Generous retries for transient 429s
        max_wait=180,        # Wait up to 3 min per retry
        timeout=300,         # 5 min timeout per call
    )

    est_calls = len(sliced) * 8  # ~8 LLM calls per sample across 3 metrics
    print(f"Metrics: {len(metrics)} | Est. LLM calls: ~{est_calls}")
    print(f"Rate-limited to 1 concurrent call.")
    print(f"Estimated time: ~{est_calls * 6 // 60} minutes\n")

    results = evaluate(
        dataset=EvaluationDataset(samples=samples),
        metrics=metrics,
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        run_config=run_config,
    )

    # Save results (append-safe: include offset in filename)
    suffix = f"_off{offset}_n{len(sliced)}" if (offset > 0 or limit) else ""
    final_output = output_path.with_stem(output_path.stem + suffix)
    final_output.parent.mkdir(parents=True, exist_ok=True)

    results_df = results.to_pandas()

    # Add sample IDs back
    ids = [s["id"] for s in sliced]
    results_df.insert(0, "id", ids)

    results_dict = {
        "aggregate": {
            col: float(results_df[col].mean())
            for col in results_df.columns
            if results_df[col].dtype in ["float64", "float32"]
        },
        "per_sample": results_df.to_dict(orient="records"),
        "meta": {
            "offset": offset,
            "limit": limit,
            "count": len(sliced),
            "total_available": total,
            "metrics": [type(m).__name__ for m in metrics],
        },
    }

    with open(final_output, "w", encoding="utf-8") as f:
        json.dump(results_dict, f, indent=2, default=str)

    print(f"\n{'='*50}")
    print("RAGAS Results (Aggregate)")
    print(f"{'='*50}")
    for metric, score in results_dict["aggregate"].items():
        print(f"  {metric:25s} {score:.4f}")
    print(f"\nResults saved to: {final_output}")


def main():
    parser = argparse.ArgumentParser(
        description="Run RAGAS evaluation (two-phase for free tier)"
    )
    parser.add_argument(
        "--benchmark", type=str, required=True, help="Path to benchmark JSON"
    )
    parser.add_argument(
        "--output", type=str, default=None, help="Output path for results JSON"
    )

    # Phase control
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Phase 1: Only collect samples and cache to disk (no RAGAS evaluation)",
    )
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Phase 2: Skip collection, load cached samples from disk",
    )

    # Batch control (for free-tier daily quota splitting)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of samples to evaluate (e.g., 10 per day for free tier)",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Start evaluation from this sample index (0-based)",
    )

    args = parser.parse_args()

    benchmark_path = BACKEND_DIR / args.benchmark
    if not benchmark_path.exists():
        benchmark_path = Path(args.benchmark)
    if not benchmark_path.exists():
        print(f"File not found: {args.benchmark}")
        sys.exit(1)

    # Determine cache path based on benchmark filename
    cache_name = benchmark_path.stem + "_samples.json"
    cache_path = CACHE_DIR / cache_name

    # --- Phase 1: Collect samples ---
    if args.cached:
        # Load from cache
        if not cache_path.exists():
            print(f"Cache not found: {cache_path}")
            print("Run with --collect-only first to generate the cache.")
            sys.exit(1)
        sample_dicts = load_cache(cache_path)
        print(f"Loaded {len(sample_dicts)} cached samples from {cache_path.name}")
    else:
        # Fresh collection
        with open(benchmark_path, encoding="utf-8") as f:
            benchmark = json.load(f)
        print(f"Loaded {len(benchmark)} entries from {benchmark_path.name}")

        sample_dicts = asyncio.run(collect_samples(benchmark))
        print(f"\nCollected {len(sample_dicts)} valid samples")

        # Always cache after collection
        save_cache(sample_dicts, cache_path)

    if not sample_dicts:
        print("No samples available. Check benchmark data and retrieval pipeline.")
        sys.exit(1)

    # --- Phase 1 only: stop here ---
    if args.collect_only:
        print(f"\n✓ Collection complete. {len(sample_dicts)} samples cached.")
        print(f"  Cache: {cache_path}")
        print(f"\nNext, run RAGAS evaluation in batches:")
        print(f"  python -m evaluation.ragas_eval --benchmark {args.benchmark} --cached --limit 10")
        print(f"  python -m evaluation.ragas_eval --benchmark {args.benchmark} --cached --limit 10 --offset 10")
        return

    # --- Phase 2: Run RAGAS ---
    output_path = (
        Path(args.output)
        if args.output
        else BACKEND_DIR / "benchmarks" / "results" / "ragas_results.json"
    )

    run_ragas_evaluation(
        sample_dicts=sample_dicts,
        output_path=output_path,
        limit=args.limit,
        offset=args.offset,
    )


if __name__ == "__main__":
    main()
