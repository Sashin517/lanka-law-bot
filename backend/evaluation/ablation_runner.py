"""Ablation study runner — runs the same benchmark under different pipeline configurations.

Uses the deterministic mode-based routing architecture. Each benchmark entry
specifies its ``mode`` field; the ablation configs control retrieval and
verification behavior at the service layer.

Usage:
    cd backend
    python -m evaluation.ablation_runner --benchmark benchmarks/datasets/full_benchmark.json
    python -m evaluation.ablation_runner --benchmark benchmarks/datasets/full_benchmark.json --configs dense_only no_reranking
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
DEFAULT_BENCHMARK = BACKEND_DIR / "benchmarks" / "datasets" / "full_benchmark.json"

# Fixed ablation subset: 2 questions per mode x 4 modes = 8 total.
# Review entries require uploaded fixture documents and are intentionally excluded
# so this runner measures RAG quality on self-contained legal QA/drafting tasks.
SAMPLES_PER_MODE = 2
TARGET_MODES = ["quick_qa", "drafting", "reasoning", "deep_research"]

# Gemini free-tier limit for gemini-3.1-flash-lite is 15 requests/minute.
# A small buffer avoids edge-of-window 429s without adding a full extra delay.
GEMINI_RPM_LIMIT = 15
GEMINI_RATE_BUFFER = 0.95
GEMINI_MODEL_NAME = "gemini-3.1-flash-lite"
ANSWER_COMPLETENESS_RETRIES = 3

# Each config specifies what to override in the pipeline
ABLATION_CONFIGS = {
    "full_pipeline": {
        "description": "Full pipeline (baseline)",
    },
    "dense_only": {
        "description": "Dense retrieval only (BM25 disabled)",
        "disable_bm25": True,
    },
    "sparse_only": {
        "description": "Sparse retrieval only (Dense embeddings disabled)",
        "disable_dense": True,
    },
    "no_reranking": {
        "description": "No cross-encoder re-ranking",
        "disable_reranking": True,
    },
    "no_parent_expansion": {
        "description": "No parent chunk expansion",
        "expand_parents": False,
    },
    "no_citation_verify": {
        "description": "No citation verification",
        "skip_verification": True,
    },
}


def select_balanced_subset(
    benchmark: list[dict],
    per_mode: int = SAMPLES_PER_MODE,
    modes: list[str] = TARGET_MODES,
) -> list[dict]:
    """Select a deterministic balanced subset from the full benchmark."""
    by_mode: dict[str, list[dict]] = defaultdict(list)

    for item in benchmark:
        category = item.get("category", "")
        mode = item.get("mode", "quick_qa")
        if category == "clarification" or mode not in modes:
            continue

        by_mode[mode].append(item)

    selected: list[dict] = []
    for mode in modes:
        chosen = by_mode.get(mode, [])[:per_mode]
        if len(chosen) < per_mode:
            logger.warning(
                "Mode '%s': only %d/%d benchmark entries available",
                mode,
                len(chosen),
                per_mode,
            )
        selected.extend(chosen)

    return selected


def install_gemini_rate_limiter() -> None:
    """Attach one shared LangChain limiter before agent nodes create LLMs."""
    try:
        import langchain_google_genai
        from langchain_core.rate_limiters import InMemoryRateLimiter
    except ImportError as exc:
        logger.warning("Could not install Gemini rate limiter: %s", exc)
        return

    original_cls = langchain_google_genai.ChatGoogleGenerativeAI
    requests_per_second = (GEMINI_RPM_LIMIT * GEMINI_RATE_BUFFER) / 60
    shared_limiter = InMemoryRateLimiter(
        requests_per_second=requests_per_second,
        check_every_n_seconds=0.2,
        max_bucket_size=1,
    )

    class RateLimitedChatGoogleGenerativeAI(original_cls):
        def __init__(self, *args, **kwargs):
            model = kwargs.get("model")
            if model == GEMINI_MODEL_NAME and kwargs.get("rate_limiter") is None:
                kwargs["rate_limiter"] = shared_limiter
            super().__init__(*args, **kwargs)

    langchain_google_genai.ChatGoogleGenerativeAI = RateLimitedChatGoogleGenerativeAI
    logger.info(
        "Installed shared Gemini limiter for %s at %.2f RPM",
        GEMINI_MODEL_NAME,
        GEMINI_RPM_LIMIT * GEMINI_RATE_BUFFER,
    )


def _source_text(source: dict) -> str:
    """Extract text used as retrieved context for RAGAS metrics."""
    return (source.get("content") or source.get("excerpt") or "").strip()


def _mean_score(results: list[dict], metric: str) -> float | None:
    scores = [
        r.get("metrics", {}).get(metric)
        for r in results
        if isinstance(r.get("metrics", {}).get(metric), (int, float))
    ]
    if not scores:
        return None
    return float(sum(scores) / len(scores))


def _aggregate_metrics(results: list[dict]) -> dict:
    metric_names = [
        "faithfulness",
        "factual_correctness",
        "context_recall",
        "context_precision",
        "answer_completeness",
    ]

    overall = {name: _mean_score(results, name) for name in metric_names}

    per_mode = {}
    for mode in TARGET_MODES:
        mode_results = [r for r in results if r.get("mode") == mode]
        if mode_results:
            per_mode[mode] = {
                name: _mean_score(mode_results, name) for name in metric_names
            }

    return {
        "overall": overall,
        "per_mode": per_mode,
        "metric_definitions": {
            "faithfulness": "Whether the answer is grounded in retrieved sources.",
            "factual_correctness": "Whether the answer matches the benchmark ground truth.",
            "context_recall": "Whether retrieved sources contain the information needed to answer.",
            "context_precision": "Whether retrieved sources are mostly relevant rather than noisy.",
            "answer_completeness": "Whether the answer covers the required legal elements in the ground truth.",
        },
    }


def _safe_float(value) -> float:
    if isinstance(value, list):
        parts = []
        for part in value:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text", ""))
        cleaned = "".join(parts).strip()
    elif isinstance(value, str):
        cleaned = value.strip()
    else:
        cleaned = str(value).strip()

    try:
        parsed = float(cleaned)
    except ValueError:
        import re

        match = re.search(r"(?<!\d)(?:0(?:\.\d+)?|1(?:\.0+)?)(?!\d)", cleaned)
        if not match:
            raise
        parsed = float(match.group(0))
    return max(0.0, min(1.0, parsed))


def score_answer_completeness(
    question: str,
    ground_truth: str,
    answer: str,
) -> float:
    """LLM judge score for legal answer completeness, 0.0-1.0.

    This is evaluation-only and uses the same rate-limited Gemini wrapper as
    pipeline and RAGAS calls.
    """
    from langchain_core.prompts import PromptTemplate
    from langchain_google_genai import ChatGoogleGenerativeAI

    prompt = PromptTemplate.from_template(
        """You are evaluating a Sri Lankan legal RAG assistant.

Question:
{question}

Ground truth answer:
{ground_truth}

Generated answer:
{answer}

Score answer completeness from 0.0 to 1.0 based only on whether the generated
answer covers the legal elements required by the ground truth: relevant Act or
case, section/rule, legal conclusion, and important qualifications.

Use this scale:
1.0 = complete, all required legal elements are present
0.7 = mostly complete, only minor legal details are missing
0.4 = partially complete, important legal elements are missing
0.0 = empty, irrelevant, or misses the central legal issue

Respond with ONLY one decimal number between 0.0 and 1.0.
"""
    )
    llm = ChatGoogleGenerativeAI(
        model=GEMINI_MODEL_NAME,
        temperature=0,
        google_api_key=os.environ.get("GOOGLE_API_KEY"),
    )
    chain = prompt | llm

    for attempt in range(ANSWER_COMPLETENESS_RETRIES):
        try:
            response = chain.invoke(
                {
                    "question": question,
                    "ground_truth": ground_truth,
                    "answer": answer,
                }
            )
            return _safe_float(response.content)
        except Exception as exc:
            if "429" not in str(exc) and "RESOURCE_EXHAUSTED" not in str(exc):
                logger.warning("Answer completeness scoring failed: %s", exc)
                return 0.0
            time.sleep(15 * (2**attempt))

    logger.warning("Answer completeness scoring exhausted retries")
    return 0.0


def add_quality_metrics(result: dict) -> dict:
    """Attach RAGAS and completeness metrics to a single ablation result."""
    metric_rows = []
    row_to_result_index = []

    for idx, item in enumerate(result["results"]):
        output = item.get("output", {})
        answer = output.get("answer", "")
        contexts = [_source_text(src) for src in output.get("sources", [])]
        contexts = [ctx for ctx in contexts if ctx]

        item["metrics"] = {
            "faithfulness": None,
            "factual_correctness": None,
            "context_recall": None,
            "context_precision": None,
            "answer_completeness": None,
        }

        if output.get("skipped") or not answer:
            continue

        # Calibrated pacing delay for completeness LLM judge
        if idx > 0:
            time.sleep(3)

        item["metrics"]["answer_completeness"] = score_answer_completeness(
            question=item.get("question", ""),
            ground_truth=item.get("ground_truth", ""),
            answer=answer,
        )

        if not contexts:
            continue

        metric_rows.append(
            {
                "user_input": item.get("question", ""),
                "retrieved_contexts": contexts,
                "response": answer,
                "reference": item.get("ground_truth", ""),
            }
        )
        row_to_result_index.append(idx)

    if metric_rows:
        from ragas import EvaluationDataset, SingleTurnSample, evaluate
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            Faithfulness,
            FactualCorrectness,
            LLMContextPrecisionWithReference,
            LLMContextRecall,
        )
        from ragas.run_config import RunConfig
        from langchain_google_genai import ChatGoogleGenerativeAI
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from langchain_huggingface import HuggingFaceEmbeddings

        samples = [
            SingleTurnSample(
                user_input=row["user_input"],
                retrieved_contexts=row["retrieved_contexts"],
                response=row["response"],
                reference=row["reference"],
            )
            for row in metric_rows
        ]
        evaluator_llm = LangchainLLMWrapper(
            ChatGoogleGenerativeAI(
                model=GEMINI_MODEL_NAME,
                temperature=0,
                google_api_key=os.environ.get("GOOGLE_API_KEY"),
            )
        )
        # Use local sentence-transformer embeddings to prevent external API requests
        evaluator_embeddings = LangchainEmbeddingsWrapper(
            HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        )
        try:
            ragas_result = evaluate(
                dataset=EvaluationDataset(samples=samples),
                metrics=[
                    Faithfulness(),
                    FactualCorrectness(),
                    LLMContextRecall(),
                    LLMContextPrecisionWithReference(),
                ],
                llm=evaluator_llm,
                embeddings=evaluator_embeddings,
                run_config=RunConfig(
                    max_workers=1,
                    max_retries=30,
                    max_wait=180,
                    timeout=300,
                ),
            )

            rows = ragas_result.to_pandas().to_dict(orient="records")
            for row, result_index in zip(rows, row_to_result_index, strict=True):
                metrics = result["results"][result_index]["metrics"]
                metrics["faithfulness"] = row.get("faithfulness")
                metrics["factual_correctness"] = row.get(
                    "factual_correctness(mode=f1)",
                    row.get("factual_correctness"),
                )
                metrics["context_recall"] = row.get("context_recall")
                metrics["context_precision"] = row.get(
                    "llm_context_precision_with_reference"
                )
        except Exception as exc:
            logger.error(
                "RAGAS metric scoring failed for %s: %s", result["config_name"], exc
            )

    result["metrics"] = _aggregate_metrics(result["results"])
    return result


async def run_single_query(
    question: str,
    config: dict,
    mode: str,
    doc_ids: list,
    matter_id: str | None,
) -> dict:
    """Run a single query with ablation config applied.

    Uses the full LangGraph pipeline so all verification nodes
    are tested properly, respecting the ablation_config in AgentState.
    """
    from evaluation.eval_pipeline import run_pipeline

    final_state = await run_pipeline(
        question=question,
        mode=mode,
        document_ids=doc_ids,
        matter_id=matter_id,
        ablation_config=config,
    )

    answer = final_state.get("markdown_content", "") or final_state.get("summary", "")
    final_response = final_state.get("final_response")
    if not answer and isinstance(final_response, dict):
        answer = final_response.get("answer", "")

    return {
        "answer": answer,
        # Some objects might be SourceChunk/CitedClaim objects if ainvoke returns them directly,
        # but langgraph usually returns dicts or we can just use dict access.
        "sources": [
            s if isinstance(s, dict) else s.model_dump()
            for s in final_state.get("retrieved_sources", [])
        ],
        "analysis": [
            c if isinstance(c, dict) else c.model_dump()
            for c in final_state.get("analysis", [])
        ],
        "confidence": final_state.get("confidence", "low"),
        "skipped": False,
    }


async def run_ablation(benchmark: list[dict], config_name: str, config: dict) -> dict:
    """Run entire benchmark under a single ablation config."""
    results = []

    for i, item in enumerate(benchmark):
        category = item.get("category", "")
        if category == "clarification":
            continue

        question = item["question"]
        mode = item.get("mode", "quick_qa")
        doc_ids = item.get("request", {}).get("document_ids", [])
        doc_ids = [d for d in doc_ids if d and not d.startswith("<")]
        matter_id = item.get("request", {}).get("matter_id")

        logger.info("  [%d/%d] %s (mode=%s)", i + 1, len(benchmark), item["id"], mode)

        # Calibrated pacing delay between sequential pipeline queries
        if i > 0:
            await asyncio.sleep(4)

        try:
            output = await run_single_query(question, config, mode, doc_ids, matter_id)
            results.append(
                {
                    "id": item["id"],
                    "category": category,
                    "mode": mode,
                    "question": question,
                    "output": output,
                    "ground_truth": item["ground_truth_answer"],
                }
            )
        except Exception as e:
            logger.error("  ✗ %s: %s", item["id"], e)
            results.append(
                {
                    "id": item["id"],
                    "category": category,
                    "mode": mode,
                    "question": question,
                    "output": {"answer": "", "skipped": True, "error": str(e)},
                    "ground_truth": item["ground_truth_answer"],
                }
            )

    return {
        "config_name": config_name,
        "description": config.get("description", ""),
        "total": len(results),
        "skipped": sum(1 for r in results if r["output"].get("skipped")),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Run ablation studies")
    parser.add_argument(
        "--benchmark",
        type=str,
        default=str(DEFAULT_BENCHMARK),
        help="Path to benchmark JSON (default: full_benchmark.json)",
    )
    parser.add_argument(
        "--configs",
        type=str,
        nargs="*",
        default=None,
        help="Specific configs to run (default: all)",
    )
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    parser.add_argument(
        "--skip-metrics",
        action="store_true",
        help="Collect ablation outputs only; skip RAGAS/completeness scoring",
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Phase 1: Collect pipeline outputs and cache raw JSON (no metrics evaluation)",
    )
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Phase 2: Load cached raw pipeline outputs and run metrics evaluation",
    )
    args = parser.parse_args()

    benchmark_path = BACKEND_DIR / args.benchmark
    if not benchmark_path.exists():
        benchmark_path = Path(args.benchmark)
    if not benchmark_path.exists():
        print(f"File not found: {args.benchmark}")
        sys.exit(1)

    with open(benchmark_path, encoding="utf-8") as f:
        benchmark = json.load(f)

    benchmark = select_balanced_subset(benchmark)
    install_gemini_rate_limiter()

    output_dir = (
        Path(args.output) if args.output else BACKEND_DIR / "benchmarks" / "results"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    configs_to_run = args.configs or list(ABLATION_CONFIGS.keys())

    mode_counts = {
        mode: sum(1 for item in benchmark if item.get("mode") == mode)
        for mode in TARGET_MODES
    }
    print(
        f"Loaded balanced subset from {benchmark_path.name}: {len(benchmark)} entries"
    )
    print(f"Mode counts: {mode_counts}")
    print(
        f"Gemini limiter: {GEMINI_RPM_LIMIT * GEMINI_RATE_BUFFER:.2f} RPM effective cap"
    )
    print(
        "Metrics: disabled"
        if (args.skip_metrics or args.collect_only)
        else "Metrics: RAGAS + answer completeness"
    )
    print(f"Running {len(configs_to_run)} ablation configs: {configs_to_run}\n")

    all_results = {}

    for config_name in configs_to_run:
        if config_name not in ABLATION_CONFIGS:
            print(f"Unknown config: {config_name}")
            continue

        config = ABLATION_CONFIGS[config_name]
        raw_output_path = output_dir / f"ablation_{config_name}_raw.json"
        final_output_path = output_dir / f"ablation_{config_name}.json"

        result = None

        # Phase 1: Collection
        if args.cached:
            # Skip collection, load from raw cache
            if not raw_output_path.exists():
                print(
                    f"Raw cache file not found: {raw_output_path.name}. Cannot run --cached."
                )
                continue
            print(f"\nLoading cached raw results for: {config_name}")
            with open(raw_output_path, encoding="utf-8") as f:
                result = json.load(f)
        else:
            # Perform collection
            print(f"\n{'='*50}")
            print(f"Running: {config_name} — {config.get('description', '')}")
            print(f"{'='*50}")
            result = asyncio.run(run_ablation(benchmark, config_name, config))

            # Save raw result cache
            with open(raw_output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"  Saved raw cache: {raw_output_path.name}")

        # Phase 2: Evaluation
        if result is not None:
            if not args.skip_metrics and not args.collect_only:
                print("  Scoring metrics with shared Gemini rate limiter...")
                result = add_quality_metrics(result)

                # Save final results
                with open(final_output_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, default=str)
                print(f"  Saved final: {final_output_path.name}")

            all_results[config_name] = result

    # Only generate comparison if metrics are not skipped/collect-only
    if not args.skip_metrics and not args.collect_only:
        # Save comparison summary
        comparison = {
            "configs": list(all_results.keys()),
            "summary": {
                name: {
                    "total": r["total"],
                    "skipped": r["skipped"],
                    "answered": r["total"] - r["skipped"],
                    "metrics": r.get("metrics", {}).get("overall", {}),
                }
                for name, r in all_results.items()
                if "metrics" in r
            },
            "per_mode_metrics": {
                name: r.get("metrics", {}).get("per_mode", {})
                for name, r in all_results.items()
                if "metrics" in r
            },
        }
        comparison_path = output_dir / "ablation_comparison.json"
        with open(comparison_path, "w", encoding="utf-8") as f:
            json.dump(comparison, f, indent=2)

        print(f"\n{'='*50}")
        print("Ablation studies evaluation complete!")
        print(f"Results in: {output_dir}")
        print(f"Comparison: {comparison_path.name}")
        print(f"{'='*50}")
    else:
        print(f"\n{'='*50}")
        print("Ablation collection complete!")
        print(f"Raw cache files located in: {output_dir}")
        print(f"{'='*50}")


if __name__ == "__main__":
    main()
