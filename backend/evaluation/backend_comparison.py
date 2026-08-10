"""Backend Comparison Runner — Pinecone vs Neo4j GraphRAG side-by-side evaluation.

Runs the same benchmark questions through both retrieval backends, collects
RAGAS metrics + multi-agent orchestration metrics + latency data for each,
and generates a comparison report.

Usage
-----
  # Full run (both backends):
  python -m evaluation.backend_comparison --benchmark benchmarks/datasets/eval_20_benchmark.json

  # Phase 1: Collect only:
  python -m evaluation.backend_comparison --benchmark benchmarks/datasets/eval_20_benchmark.json --collect-only

  # Phase 2: Evaluate from cache:
  python -m evaluation.backend_comparison --benchmark benchmarks/datasets/eval_20_benchmark.json --cached

  # Single backend only:
  python -m evaluation.backend_comparison --benchmark benchmarks/datasets/eval_20_benchmark.json --backends pinecone
"""

import argparse
import asyncio
import importlib
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
CACHE_DIR = BACKEND_DIR / "benchmarks" / "results" / "_comparison_cache"
RESULTS_DIR = BACKEND_DIR / "benchmarks" / "results"

SUPPORTED_BACKENDS = ["pinecone", "neo4j"]
COLLECTION_DELAY_S = 5


# ── Backend switching ────────────────────────────────────────────


def _switch_retrieval_backend(backend: str) -> None:
    """Hot-swap the retrieval backend by updating settings and reloading the shared module.

    This modifies the ``RETRIEVAL_BACKEND`` setting and forces
    ``app.agents.shared`` to re-initialize its retrieval service
    singleton.
    """
    from app.core.config import settings

    settings.RETRIEVAL_BACKEND = backend
    os.environ["RETRIEVAL_BACKEND"] = backend

    # Force re-initialization of the shared retrieval service
    import app.agents.shared as shared_mod

    shared_mod.retrieval_service = shared_mod.get_configured_retrieval_service()

    logger.info("Switched retrieval backend to: %s", backend)


# ── Collection ───────────────────────────────────────────────────


async def collect_backend_samples(
    entries: list[dict],
    backend: str,
) -> list[dict]:
    """Run each entry through the LangGraph pipeline with a specific backend.

    Returns serializable dicts with response, contexts, execution_trace,
    and timing data.
    """
    from evaluation.eval_pipeline import run_pipeline

    _switch_retrieval_backend(backend)

    samples: list[dict] = []

    for i, item in enumerate(entries):
        question = item["question"]
        mode = item.get("mode", "quick_qa")
        doc_ids = item.get("request", {}).get("document_ids", [])
        doc_ids = [d for d in doc_ids if d and not d.startswith("<")]
        matter_id = item.get("request", {}).get("matter_id")

        # Skip review entries that require fixture documents not yet uploaded
        if item.get("requires_user_document") and not doc_ids:
            logger.info("[%d/%d] Skipping %s (requires fixture upload)", i + 1, len(entries), item["id"])
            continue

        logger.info(
            "[%d/%d] Collecting [%s]: %s (mode=%s)",
            i + 1, len(entries), backend.upper(), item["id"], mode,
        )

        if i > 0:
            await asyncio.sleep(COLLECTION_DELAY_S)

        try:
            start_time = time.time()
            final_state = await run_pipeline(
                question=question,
                mode=mode,
                document_ids=doc_ids,
                matter_id=matter_id,
            )
            e2e_seconds = time.time() - start_time

            # Extract response text
            response_text = (
                final_state.get("markdown_content", "")
                or final_state.get("summary", "")
            )
            if not response_text:
                fr = final_state.get("final_response")
                if isinstance(fr, dict):
                    response_text = fr.get("answer", "")

            # Extract retrieved contexts
            retrieved_sources = final_state.get("retrieved_sources", [])
            retrieved_contexts: list[str] = []
            sources_data: list[dict] = []
            for src in retrieved_sources:
                if hasattr(src, "content"):
                    text = src.content or src.excerpt or ""
                    src_dict = src.model_dump() if hasattr(src, "model_dump") else {}
                elif isinstance(src, dict):
                    text = src.get("content", "") or src.get("excerpt", "")
                    src_dict = src
                else:
                    text = str(src)
                    src_dict = {}
                if text.strip():
                    retrieved_contexts.append(text.strip())
                sources_data.append(src_dict)

            # Extract execution trace
            fr = final_state.get("final_response")
            execution_trace = {}
            if isinstance(fr, dict):
                execution_trace = fr.get("execution_trace", {})

            # Extract grounding info
            grounding = final_state.get("grounding", {})
            if hasattr(grounding, "model_dump"):
                grounding = grounding.model_dump()
            elif not isinstance(grounding, dict):
                grounding = {}

            samples.append({
                "id": item["id"],
                "mode": mode,
                "hop_type": item.get("hop_type", "single_hop"),
                "difficulty": item.get("difficulty", "medium"),
                "user_input": question,
                "retrieved_contexts": retrieved_contexts,
                "response": response_text,
                "reference": item.get("ground_truth_answer", ""),
                "sources": sources_data,
                "execution_trace": execution_trace,
                "grounding": grounding,
                "retry_count": final_state.get("retry_count", 0),
                "confidence": final_state.get("confidence", ""),
                "e2e_seconds": round(e2e_seconds, 3),
                "backend": backend,
                # Benchmark entry fields for evaluator use
                "expected_plan_type": item.get("expected_plan_type", "fast_path"),
                "expected_agents": item.get("expected_agents", []),
            })

            logger.info(
                "  ✓ [%s] %s: %d contexts, %d char response, %.1fs",
                backend, item["id"],
                len(retrieved_contexts), len(response_text), e2e_seconds,
            )

        except Exception as e:
            logger.error("  ✗ [%s] %s: %s", backend, item["id"], e)
            continue

    return samples


# ── RAGAS Evaluation ─────────────────────────────────────────────


def run_ragas_on_samples(sample_dicts: list[dict]) -> dict:
    """Run RAGAS metrics on collected samples."""
    from ragas import evaluate, EvaluationDataset, SingleTurnSample
    from ragas.metrics import (
        Faithfulness,
        FactualCorrectness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
    )
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.run_config import RunConfig
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_huggingface import HuggingFaceEmbeddings

    # Filter samples with contexts
    valid = [s for s in sample_dicts if s.get("retrieved_contexts")]
    if not valid:
        return {"error": "No valid samples with contexts"}

    samples = [
        SingleTurnSample(
            user_input=s["user_input"],
            retrieved_contexts=s["retrieved_contexts"],
            response=s["response"],
            reference=s["reference"],
        )
        for s in valid
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

    metrics = [
        Faithfulness(),
        FactualCorrectness(),
        LLMContextRecall(),
        LLMContextPrecisionWithReference(),
    ]

    logger.info("Running RAGAS on %d samples (4 metrics)...", len(samples))

    results = evaluate(
        dataset=EvaluationDataset(samples=samples),
        metrics=metrics,
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        run_config=RunConfig(
            max_workers=1,
            max_retries=30,
            max_wait=180,
            timeout=300,
        ),
    )

    results_df = results.to_pandas()
    metric_cols = [
        col for col in results_df.columns
        if results_df[col].dtype in ["float64", "float32"]
    ]

    overall = {col: float(results_df[col].mean()) for col in metric_cols}

    # Per-mode aggregation
    modes_list = [s["mode"] for s in valid]
    results_df["mode"] = modes_list

    per_mode = {}
    for mode in set(modes_list):
        mode_df = results_df[results_df["mode"] == mode]
        if not mode_df.empty:
            per_mode[mode] = {col: float(mode_df[col].mean()) for col in metric_cols}

    # Per-hop-type aggregation
    hop_types = [s.get("hop_type", "single_hop") for s in valid]
    results_df["hop_type"] = hop_types

    per_hop = {}
    for hop in set(hop_types):
        hop_df = results_df[results_df["hop_type"] == hop]
        if not hop_df.empty:
            per_hop[hop] = {col: float(hop_df[col].mean()) for col in metric_cols}

    return {
        "overall": overall,
        "per_mode": per_mode,
        "per_hop_type": per_hop,
        "per_sample": results_df.to_dict(orient="records"),
    }


# ── Multi-Agent Metrics ──────────────────────────────────────────


def evaluate_agent_metrics(
    sample_dicts: list[dict],
) -> dict:
    """Run multi-agent evaluators on collected samples."""
    from evaluation.evaluators.plan_accuracy import plan_accuracy_evaluator
    from evaluation.evaluators.agent_goal_accuracy import agent_goal_accuracy_evaluator
    from evaluation.evaluators.orchestration_metrics import (
        grounding_pass_rate,
        planning_appropriateness,
        source_diversity,
        latency_metrics,
    )

    plan_scores = []
    goal_scores = []
    grounding_rates = []
    planning_scores = []
    diversity_data = []
    latency_data = []

    for i, sample in enumerate(sample_dicts):
        trace = sample.get("execution_trace", {})
        entry = {
            "expected_plan_type": sample.get("expected_plan_type", "fast_path"),
            "expected_agents": sample.get("expected_agents", []),
        }

        # Plan accuracy
        plan = plan_accuracy_evaluator(trace, entry)
        plan_scores.append(plan)

        # Goal accuracy (with rate limiting)
        if i > 0:
            time.sleep(3)
        goal = agent_goal_accuracy_evaluator(
            question=sample["user_input"],
            mode=sample["mode"],
            response=sample["response"],
            ground_truth=sample["reference"],
            execution_trace=trace,
        )
        goal_scores.append(goal)

        # Grounding
        grd = grounding_pass_rate(
            grounding_score=sample.get("grounding", {}).get("grounding_score", 0),
            retry_count=sample.get("retry_count", 0),
        )
        grounding_rates.append(grd)

        # Planning appropriateness
        pln = planning_appropriateness(trace, entry["expected_plan_type"])
        planning_scores.append(pln)

        # Source diversity
        div = source_diversity(sample.get("sources", []))
        diversity_data.append(div)

        # Latency
        lat = latency_metrics(sample.get("e2e_seconds", 0))
        latency_data.append(lat)

    # Aggregate
    def _mean(scores: list[dict], key: str) -> float | None:
        vals = [s[key] for s in scores if isinstance(s.get(key), (int, float))]
        return round(sum(vals) / len(vals), 4) if vals else None

    return {
        "plan_accuracy": _mean(plan_scores, "plan_accuracy"),
        "plan_type_match": _mean(plan_scores, "plan_type_match"),
        "agent_sequence_f1": _mean(plan_scores, "agent_sequence_f1"),
        "goal_accuracy": _mean(goal_scores, "goal_accuracy"),
        "grounding_first_pass_rate": _mean(grounding_rates, "first_pass"),
        "planning_appropriateness": _mean(planning_scores, "appropriate"),
        "mean_e2e_ms": _mean(latency_data, "e2e_ms"),
        "mean_unique_acts": _mean(diversity_data, "unique_acts"),
        "per_sample": {
            "plan": plan_scores,
            "goal": goal_scores,
            "grounding": grounding_rates,
            "planning": planning_scores,
            "diversity": diversity_data,
            "latency": latency_data,
        },
    }


# ── Comparison Report ────────────────────────────────────────────


def generate_comparison(results: dict, output_path: Path) -> None:
    """Generate side-by-side comparison JSON from both backend results."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    comparison = {
        "backends": list(results.keys()),
        "ragas_comparison": {},
        "agent_metrics_comparison": {},
        "hop_type_comparison": {},
        "latency_comparison": {},
    }

    for backend, data in results.items():
        ragas = data.get("ragas", {})
        agent = data.get("agent", {})

        comparison["ragas_comparison"][backend] = ragas.get("overall", {})
        comparison["agent_metrics_comparison"][backend] = {
            k: v for k, v in agent.items() if k != "per_sample"
        }
        comparison["hop_type_comparison"][backend] = ragas.get("per_hop_type", {})
        comparison["latency_comparison"][backend] = {
            "mean_e2e_ms": agent.get("mean_e2e_ms"),
        }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, default=str)

    # Print summary
    print(f"\n{'='*70}")
    print("BACKEND COMPARISON RESULTS")
    print(f"{'='*70}")

    for backend in results:
        ragas_overall = results[backend].get("ragas", {}).get("overall", {})
        agent_metrics = results[backend].get("agent", {})
        print(f"\n  [{backend.upper()}]")
        for metric, score in ragas_overall.items():
            print(f"    {metric:40s} {score:.4f}")
        print(f"    {'plan_accuracy':40s} {agent_metrics.get('plan_accuracy', 'N/A')}")
        print(f"    {'goal_accuracy':40s} {agent_metrics.get('goal_accuracy', 'N/A')}")
        print(f"    {'mean_e2e_ms':40s} {agent_metrics.get('mean_e2e_ms', 'N/A')}")

    print(f"\n  Saved to: {output_path}")
    print(f"{'='*70}")


# ── Cache management ─────────────────────────────────────────────


def save_cache(samples: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(samples, f, indent=2, ensure_ascii=False, default=str)
    logger.info("Cached %d samples → %s", len(samples), path.name)


def load_cache(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── CLI ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Run Pinecone vs Neo4j backend comparison evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--benchmark", type=str, required=True,
        help="Path to benchmark JSON",
    )
    parser.add_argument(
        "--backends", type=str, nargs="*", default=SUPPORTED_BACKENDS,
        help=f"Backends to evaluate (default: {SUPPORTED_BACKENDS})",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output path for comparison results JSON",
    )
    parser.add_argument(
        "--collect-only", action="store_true",
        help="Phase 1: Collect pipeline outputs only (no evaluation)",
    )
    parser.add_argument(
        "--cached", action="store_true",
        help="Phase 2: Load cached outputs, skip collection",
    )
    args = parser.parse_args()

    # Resolve benchmark path
    benchmark_path = BACKEND_DIR / args.benchmark
    if not benchmark_path.exists():
        benchmark_path = Path(args.benchmark)
    if not benchmark_path.exists():
        print(f"File not found: {args.benchmark}")
        sys.exit(1)

    with open(benchmark_path, encoding="utf-8") as f:
        entries = json.load(f)

    print(f"Loaded {len(entries)} entries from {benchmark_path.name}")
    print(f"Backends: {args.backends}")

    all_results = {}

    for backend in args.backends:
        if backend not in SUPPORTED_BACKENDS:
            print(f"Unknown backend: {backend}")
            continue

        cache_path = CACHE_DIR / f"comparison_{backend}_samples.json"

        if args.cached:
            if not cache_path.exists():
                print(f"Cache not found for {backend}: {cache_path}")
                continue
            samples = load_cache(cache_path)
            print(f"\nLoaded {len(samples)} cached samples for [{backend.upper()}]")
        else:
            print(f"\n{'='*50}")
            print(f"Collecting: [{backend.upper()}]")
            print(f"{'='*50}")
            samples = asyncio.run(collect_backend_samples(entries, backend))
            save_cache(samples, cache_path)
            print(f"Collected {len(samples)} samples for [{backend.upper()}]")

        if args.collect_only:
            continue

        if not samples:
            print(f"No valid samples for {backend}")
            continue

        # Run evaluations
        print(f"\n  Evaluating [{backend.upper()}] RAGAS metrics...")
        ragas_results = run_ragas_on_samples(samples)

        print(f"  Evaluating [{backend.upper()}] agent metrics...")
        agent_results = evaluate_agent_metrics(samples)

        all_results[backend] = {
            "ragas": ragas_results,
            "agent": agent_results,
            "sample_count": len(samples),
        }

        # Save individual backend results
        backend_output = RESULTS_DIR / f"comparison_{backend}_results.json"
        with open(backend_output, "w", encoding="utf-8") as f:
            json.dump(all_results[backend], f, indent=2, default=str)
        print(f"  Saved: {backend_output.name}")

    if args.collect_only:
        print(f"\n✓ Collection complete for {args.backends}")
        return

    if len(all_results) >= 1:
        output_path = (
            Path(args.output) if args.output
            else RESULTS_DIR / "backend_comparison.json"
        )
        generate_comparison(all_results, output_path)


if __name__ == "__main__":
    main()
