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
import hashlib
import json
import logging
import math
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass

from pathlib import Path

from dotenv import load_dotenv
from evaluation.ablation import AblationConfigurationError

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BENCHMARK = BACKEND_DIR / "benchmarks" / "datasets" / "full_benchmark.json"

# Fixed ablation subset: 5 questions per mode x 4 modes = 20 total.
# Review entries require uploaded fixture documents and are intentionally excluded
# so this runner measures RAG quality on self-contained legal QA/drafting tasks.
SAMPLES_PER_MODE = 5
TARGET_MODES = ["quick_qa", "drafting", "reasoning", "deep_research"]

# Gemini free-tier limit for gemini-3.1-flash-lite is 15 requests/minute.
# A small buffer avoids edge-of-window 429s without adding a full extra delay. 
GEMINI_RPM_LIMIT = 15
GEMINI_RATE_BUFFER = 0.95
GEMINI_MODEL_NAME = "gemini-3.1-flash-lite-preview"
ANSWER_COMPLETENESS_RETRIES = 3
ANSWER_COMPLETENESS_RETRY_BASE_SECONDS = 5
CACHE_SCHEMA_VERSION = 3
CITATION_ANCHOR_RE = re.compile(r"\[(?:LAW|DOC)-\d+\]")


class MetricEvaluationError(RuntimeError):
    """Raised when metric coverage is incomplete or an evaluator fails."""


@dataclass(frozen=True)
class MetricOutcome:
    """A metric value that distinguishes evaluator failure from score zero."""

    value: float | None
    error: str | None = None


# Each config specifies what to override in the pipeline.
# All ablation configurations enforce fast-path single-agent dispatch (force_fast_path: True)
# to evaluate task completion using the selected mode agent directly (matching ragas_eval.py).
ABLATION_CONFIGS = {
    "full_pipeline": {
        "description": "Full pipeline (baseline - fast-path single agent)",
        "force_fast_path": True,
    },
    "dense_only": {
        "description": "Dense retrieval only (BM25 disabled)",
        "disable_bm25": True,
        "force_fast_path": True,
    },
    "sparse_only": {
        "description": "Sparse retrieval only (Dense embeddings disabled)",
        "disable_dense": True,
        "force_fast_path": True,
    },
    "no_reranking": {
        "description": "No cross-encoder re-ranking",
        "disable_reranking": True,
        "force_fast_path": True,
    },
    "no_parent_expansion": {
        "description": "No parent chunk expansion",
        "expand_parents": False,
        "force_fast_path": True,
    },
    "no_citation_verify": {
        "description": "No citation verification",
        "skip_verification": True,
        "force_fast_path": True,
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


def benchmark_identity(benchmark: list[dict], benchmark_path: Path) -> dict:
    """Build a stable identity for the exact selected benchmark records."""
    canonical = json.dumps(
        benchmark,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "name": benchmark_path.stem,
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "record_count": len(benchmark),
        "record_ids": [item.get("id") for item in benchmark],
    }


def study_directory_name(identity: dict) -> str:
    """Return a filesystem-safe, content-addressed study directory name."""
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", identity["name"]).strip("-._")
    return f"{safe_name or 'benchmark'}-{identity['sha256'][:12]}"


def build_run_metadata(
    identity: dict,
    config_name: str,
    config: dict,
    retrieval_effects: dict,
) -> dict:
    """Create deterministic cache metadata used for strict compatibility checks."""
    from app.core.config import settings

    effective_config = {k: v for k, v in config.items() if k != "description"}
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "benchmark": identity,
        "config_name": config_name,
        "ablation_config": effective_config,
        "retrieval_effects": retrieval_effects,
        "pipeline_model": settings.LLM_MODEL_NAME,
        "evaluation_model": GEMINI_MODEL_NAME,
    }


def validate_cached_result(cached: dict, expected_metadata: dict) -> None:
    """Reject cache data not produced for this exact study configuration."""
    actual_metadata = cached.get("run_metadata")
    if actual_metadata != expected_metadata:
        raise ValueError(
            "Cached result metadata does not match the requested benchmark, "
            "configuration, retrieval backend, or evaluator model"
        )

    expected_ids = expected_metadata["benchmark"]["record_ids"]
    actual_ids = [item.get("id") for item in cached.get("results", [])]
    if actual_ids != expected_ids:
        raise ValueError(
            "Cached result record IDs do not match the selected benchmark records"
        )

    if cached.get("total") != len(expected_ids):
        raise ValueError("Cached result count does not match benchmark metadata")


def preflight_ablation_config(config: dict) -> dict:
    """Validate that the configured backend can apply the requested ablation."""
    from evaluation.ablation import (
        RETRIEVAL_ABLATION_KEYS,
        describe_neo4j_effects,
        describe_pinecone_effects,
    )
    from app.core.config import settings

    supported_keys = set(RETRIEVAL_ABLATION_KEYS) | {
        "description",
        "skip_verification",
        "force_fast_path",
    }
    unknown_keys = sorted(set(config) - supported_keys)
    if unknown_keys:
        raise AblationConfigurationError(
            f"Unsupported ablation option(s): {', '.join(unknown_keys)}"
        )

    backend = getattr(settings, "RETRIEVAL_BACKEND", "pinecone").lower()
    if backend == "neo4j":
        effects = describe_neo4j_effects(config)
    elif backend in {"pinecone", "both"}:
        effects = describe_pinecone_effects(
            config,
            # Dense and BM25 fields are mandatory parts of one validated index.
            bm25_available=bool(settings.PINECONE_LEGAL_INDEX_HOST),
            reranking_available=bool(settings.PINECONE_LEGAL_INDEX_HOST),
        )
    else:
        raise AblationConfigurationError(
            f"Unsupported RETRIEVAL_BACKEND for ablation: {backend!r}"
        )

    effects["citation_verification_enabled"] = not bool(
        config.get("skip_verification", False)
    )
    effects["planning_enabled"] = False  # Enforced fast-path dispatch for evaluation
    return effects


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
    """Extract source text used as context for RAGAS metrics."""
    return (source.get("content") or source.get("excerpt") or "").strip()


def _cited_contexts(answer: str, sources: list[dict]) -> list[str]:
    """Return contexts whose citation anchors occur in the final answer.

    Extracts both bracketed (e.g. [LAW-1]) and unbracketed (e.g. LAW-1) anchors.
    If no specific citation anchors match or are present, falls back to all
    retrieved source contexts to prevent false zero-context evaluation penalties.
    """
    if not answer or not sources:
        return [_source_text(s) for s in sources if _source_text(s)]

    cited_ids = set(CITATION_ANCHOR_RE.findall(answer))
    unbracketed = set(re.findall(r"\b(?:LAW|DOC)-\d+\b", answer, re.IGNORECASE))

    all_cited: set[str] = set()
    for c in cited_ids:
        c_clean = c.strip().upper()
        all_cited.add(c_clean)
        all_cited.add(c_clean.strip("[]"))
    for u in unbracketed:
        u_clean = u.strip().upper()
        all_cited.add(f"[{u_clean}]")
        all_cited.add(u_clean)

    contexts: list[str] = []
    seen: set[str] = set()
    for source in sources:
        cid = source.get("citation_id", "")
        cid_upper = cid.upper() if isinstance(cid, str) else ""
        cid_norm = f"[{cid_upper}]" if not cid_upper.startswith("[") else cid_upper

        if all_cited and (cid_upper not in all_cited and cid_norm not in all_cited):
            continue

        context = _source_text(source)
        if context and context not in seen:
            seen.add(context)
            contexts.append(context)

    # Fallback to all retrieved source contexts if no cited contexts matched
    if not contexts:
        for source in sources:
            context = _source_text(source)
            if context and context not in seen:
                seen.add(context)
                contexts.append(context)

    return contexts


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
        "drafting_rubric_score",
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
            "faithfulness": "Whether the answer is grounded in sources cited by the answer.",
            "factual_correctness": "Whether the answer matches the benchmark ground truth.",
            "context_recall": "Whether cited sources contain the information needed to answer.",
            "context_precision": "Whether cited sources are mostly relevant rather than noisy.",
            "answer_completeness": "Whether the answer covers the required legal elements in the ground truth.",
            "drafting_rubric_score": "Whether the generated legal draft satisfies the requirements rubric.",
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


def _is_retryable_judge_error(exc: Exception) -> bool:
    """Return whether an evaluator failure is likely transient or reparable."""
    if isinstance(exc, (ConnectionError, TimeoutError, ValueError)):
        return True

    message = str(exc).lower()
    permanent_markers = (
        "api key not valid",
        "invalid api key",
        "permission denied",
        "unauthenticated",
        "invalid argument",
        "model not found",
        "404 not found",
    )
    if any(marker in message for marker in permanent_markers):
        return False

    transient_markers = (
        "429",
        "500",
        "502",
        "503",
        "504",
        "resource_exhausted",
        "server disconnected",
        "connection reset",
        "connection aborted",
        "connection closed",
        "temporarily unavailable",
        "service unavailable",
        "deadline exceeded",
        "timed out",
        "timeout",
        "remote protocol",
        "internal server error",
    )
    return any(marker in message for marker in transient_markers)


def _invoke_completeness_judge_with_retries(invoke) -> MetricOutcome:
    """Invoke the scalar judge with bounded exponential-backoff retries."""
    last_error = "Unknown evaluator failure"
    for attempt in range(ANSWER_COMPLETENESS_RETRIES):
        try:
            response = invoke()
            return MetricOutcome(value=_safe_float(response.content))
        except Exception as exc:
            last_error = str(exc)
            if not _is_retryable_judge_error(exc):
                logger.warning("Answer completeness scoring failed: %s", exc)
                return MetricOutcome(value=None, error=str(exc))

            logger.warning(
                "Transient answer completeness failure (attempt %d/%d): %s",
                attempt + 1,
                ANSWER_COMPLETENESS_RETRIES,
                exc,
            )
            if attempt < ANSWER_COMPLETENESS_RETRIES - 1:
                time.sleep(ANSWER_COMPLETENESS_RETRY_BASE_SECONDS * (2**attempt))

    logger.warning("Answer completeness scoring exhausted retries: %s", last_error)
    return MetricOutcome(
        value=None,
        error=(
            f"Answer completeness scoring failed after "
            f"{ANSWER_COMPLETENESS_RETRIES} attempts: {last_error}"
        ),
    )


def score_answer_completeness(
    question: str,
    ground_truth: str,
    answer: str,
) -> MetricOutcome:
    """Return a completeness score or an explicit evaluator error."""
    try:
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
    except Exception as exc:
        logger.warning("Answer completeness evaluator setup failed: %s", exc)
        return MetricOutcome(value=None, error=f"Evaluator setup failed: {exc}")

    payload = {
        "question": question,
        "ground_truth": ground_truth,
        "answer": answer,
    }
    return _invoke_completeness_judge_with_retries(lambda: chain.invoke(payload))


def _finite_metric(value) -> float | None:
    """Normalize evaluator output, accepting only finite 0.0-1.0 scores."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) and 0.0 <= numeric <= 1.0 else None


def _run_ragas_evaluation(
    metric_rows: list[dict],
    metric_names: tuple[str, ...] = (
        "faithfulness",
        "factual_correctness",
        "context_recall",
        "context_precision",
    ),
) -> list[dict]:
    """Run RAGAS setup and scoring as one failure boundary."""
    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        Faithfulness,
        FactualCorrectness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
    )
    from ragas.run_config import RunConfig
    from langchain_google_genai import ChatGoogleGenerativeAI
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
    evaluator_embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    )
    metric_factories = {
        "faithfulness": Faithfulness,
        "factual_correctness": FactualCorrectness,
        "context_recall": LLMContextRecall,
        "context_precision": LLMContextPrecisionWithReference,
    }
    unknown_metrics = sorted(set(metric_names) - set(metric_factories))
    if unknown_metrics:
        raise ValueError(f"Unknown RAGAS metric(s): {', '.join(unknown_metrics)}")

    ragas_result = evaluate(
        dataset=EvaluationDataset(samples=samples),
        metrics=[metric_factories[name]() for name in metric_names],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        run_config=RunConfig(
            max_workers=1,
            max_retries=30,
            max_wait=180,
            timeout=300,
        ),
    )
    return ragas_result.to_pandas().to_dict(orient="records")


def add_quality_metrics(result: dict) -> dict:
    """Attach complete metrics or raise instead of publishing partial results."""
    metric_rows = []
    row_to_result_index = []
    uncited_factual_rows = []
    uncited_to_result_index = []
    evaluation_errors: list[str] = []

    for idx, item in enumerate(result["results"]):
        output = item.get("output", {})
        answer = output.get("answer", "")
        sources = output.get("sources", [])
        contexts = _cited_contexts(answer, sources)
        mode = item.get("mode") or item.get("category", "")
        output["retrieved_context_count"] = sum(
            1 for source in sources if _source_text(source)
        )
        output["cited_context_count"] = len(contexts)

        existing_metrics = item.get("metrics") or {}
        item["metrics"] = {
            "faithfulness": _finite_metric(existing_metrics.get("faithfulness")),
            "factual_correctness": _finite_metric(
                existing_metrics.get("factual_correctness")
            ),
            "context_recall": _finite_metric(existing_metrics.get("context_recall")),
            "context_precision": _finite_metric(
                existing_metrics.get("context_precision")
            ),
            "answer_completeness": _finite_metric(
                existing_metrics.get("answer_completeness")
            ),
            "drafting_rubric_score": _finite_metric(
                existing_metrics.get("drafting_rubric_score")
            ),
        }
        item["metric_errors"] = item.get("metric_errors") or {}
        item["metric_notes"] = item.get("metric_notes") or {}

        if output.get("skipped") or not answer:
            continue

        # --- DRAFTING SAMPLES ROUTING ---
        if mode == "drafting":
            if item["metrics"]["drafting_rubric_score"] is None:
                try:
                    if idx > 0:
                        time.sleep(3)

                    all_contexts = [_source_text(s) for s in sources if _source_text(s)]

                    from evaluation.custom_metrics import DraftingRubricEvaluator
                    from langchain_google_genai import ChatGoogleGenerativeAI

                    drafting_model = ChatGoogleGenerativeAI(
                        model=GEMINI_MODEL_NAME,
                        temperature=0,
                        google_api_key=os.environ.get("GOOGLE_API_KEY"),
                    )
                    evaluator = DraftingRubricEvaluator(llm=drafting_model)
                    res = evaluator.evaluate_sample(
                        draft=answer,
                        rubric=item.get("ground_truth", ""),
                        contexts=all_contexts,
                    )

                    item["metrics"]["drafting_rubric_score"] = float(
                        res.get("score", 0.0)
                    )
                    item["metric_notes"]["drafting_reasoning"] = res.get(
                        "reasoning", ""
                    )
                except Exception as exc:
                    logger.error(
                        "Drafting rubric scoring failed for %s: %s", item.get("id"), exc
                    )
                    item["metric_errors"]["drafting_rubric_score"] = str(exc)
                    evaluation_errors.append(
                        f"{item.get('id')}: drafting_rubric_score: {exc}"
                    )
            continue

        # --- NON-DRAFTING SAMPLES ROUTING ---
        if item["metrics"]["answer_completeness"] is None:
            if idx > 0:
                time.sleep(3)

            completeness = score_answer_completeness(
                question=item.get("question", ""),
                ground_truth=item.get("ground_truth", ""),
                answer=answer,
            )
            item["metrics"]["answer_completeness"] = completeness.value
            if completeness.error:
                item["metric_errors"]["answer_completeness"] = completeness.error
                evaluation_errors.append(
                    f"{item.get('id')}: answer_completeness: {completeness.error}"
                )

        if not contexts:
            # This is a measurable system outcome (often an abstention after
            # weak retrieval), not an evaluator failure. With a non-empty
            # reference answer, an empty cited set has zero cited-context
            # coverage and precision. Factual correctness remains independently
            # judgeable from the answer/reference pair.
            item["metrics"]["faithfulness"] = 0.0
            item["metrics"]["context_recall"] = 0.0
            item["metrics"]["context_precision"] = 0.0
            item["metric_notes"]["cited_contexts"] = (
                "No resolvable citations in the final answer; source-dependent "
                "metrics scored as 0.0"
            )
            if item["metrics"].get("factual_correctness") is None:
                uncited_factual_rows.append(
                    {
                        "user_input": item.get("question", ""),
                        "retrieved_contexts": [],
                        "response": answer,
                        "reference": item.get("ground_truth", ""),
                    }
                )
                uncited_to_result_index.append(idx)
            continue

        if item["metrics"].get("faithfulness") is None:
            metric_rows.append(
                {
                    "user_input": item.get("question", ""),
                    "retrieved_contexts": contexts,
                    "response": answer,
                    "reference": item.get("ground_truth", ""),
                }
            )
            row_to_result_index.append(idx)

    if evaluation_errors:
        result["metrics"] = _aggregate_metrics(result["results"])
        result["metric_status"] = {
            "status": "failed",
            "stage": "pre_ragas",
            "error_count": len(evaluation_errors),
            "errors": evaluation_errors,
        }
        raise MetricEvaluationError(
            f"Metric evaluation incomplete for {result['config_name']}: "
            f"{len(evaluation_errors)} pre-RAGAS error(s)"
        )

    if metric_rows:
        try:
            rows = _run_ragas_evaluation(metric_rows)
            for row, result_index in zip(rows, row_to_result_index, strict=True):
                target = result["results"][result_index]
                metrics = target["metrics"]
                raw_values = {
                    "faithfulness": row.get("faithfulness"),
                    "factual_correctness": row.get(
                        "factual_correctness(mode=f1)",
                        row.get("factual_correctness"),
                    ),
                    "context_recall": row.get("context_recall"),
                    "context_precision": row.get(
                        "llm_context_precision_with_reference"
                    ),
                }
                for metric_name, raw_value in raw_values.items():
                    value = _finite_metric(raw_value)
                    metrics[metric_name] = value
                    if value is None:
                        error = f"Evaluator returned invalid value: {raw_value!r}"
                        target["metric_errors"][metric_name] = error
                        evaluation_errors.append(
                            f"{target.get('id')}: {metric_name}: {error}"
                        )
        except Exception as exc:
            logger.error(
                "RAGAS metric scoring failed for %s: %s", result["config_name"], exc
            )
            for result_index in row_to_result_index:
                target = result["results"][result_index]
                target["metric_errors"]["ragas"] = str(exc)
            evaluation_errors.append(f"RAGAS batch failed: {exc}")

    if uncited_factual_rows:
        try:
            rows = _run_ragas_evaluation(
                uncited_factual_rows,
                metric_names=("factual_correctness",),
            )
            for row, result_index in zip(rows, uncited_to_result_index, strict=True):
                target = result["results"][result_index]
                raw_value = row.get(
                    "factual_correctness(mode=f1)",
                    row.get("factual_correctness"),
                )
                value = _finite_metric(raw_value)
                target["metrics"]["factual_correctness"] = value
                if value is None:
                    error = f"Evaluator returned invalid value: {raw_value!r}"
                    target["metric_errors"]["factual_correctness"] = error
                    evaluation_errors.append(
                        f"{target.get('id')}: factual_correctness: {error}"
                    )
        except Exception as exc:
            logger.error(
                "RAGAS factual-correctness scoring failed for uncited answers "
                "in %s: %s",
                result["config_name"],
                exc,
            )
            for result_index in uncited_to_result_index:
                target = result["results"][result_index]
                target["metric_errors"]["factual_correctness"] = str(exc)
            evaluation_errors.append(
                f"RAGAS uncited-answer factual-correctness batch failed: {exc}"
            )

    result["metrics"] = _aggregate_metrics(result["results"])
    answered_count = 0
    for item in result["results"]:
        output = item.get("output", {})
        if output.get("skipped") or not output.get("answer"):
            continue
        answered_count += 1
        mode = item.get("mode") or item.get("category", "")
        if mode == "drafting":
            required_metrics = ("drafting_rubric_score",)
        else:
            required_metrics = (
                "faithfulness",
                "factual_correctness",
                "context_recall",
                "context_precision",
                "answer_completeness",
            )
        missing = [
            metric
            for metric in required_metrics
            if _finite_metric(item.get("metrics", {}).get(metric)) is None
        ]
        if missing:
            error = f"Missing required metrics: {', '.join(missing)}"
            item["metric_errors"]["coverage"] = error
            evaluation_errors.append(f"{item.get('id')}: {error}")

    if answered_count == 0:
        evaluation_errors.append(
            "No answered records were available for metric scoring"
        )

    if evaluation_errors:
        result["metric_status"] = {
            "status": "failed",
            "error_count": len(evaluation_errors),
            "errors": evaluation_errors,
        }
        raise MetricEvaluationError(
            f"Metric evaluation incomplete for {result['config_name']}: "
            f"{len(evaluation_errors)} error(s)"
        )

    result["metric_status"] = {
        "status": "complete",
        "evaluated_records": answered_count,
    }
    return result


async def run_single_query(
    question: str,
    config: dict,
    mode: str,
    doc_ids: list,
    matter_id: str | None,
) -> dict:
    """Run a single query with ablation config applied using fast-path mode dispatch.

    Enforces fast-path dispatch (force_fast_path=True) so task completion is performed
    directly by the single worker agent for the selected mode, matching ragas_eval.py.
    """
    from evaluation.eval_pipeline import run_pipeline

    ablation_payload = {"force_fast_path": True, **(config or {})}

    final_state = await run_pipeline(
        question=question,
        mode=mode,
        document_ids=doc_ids,
        matter_id=matter_id,
        ablation_config=ablation_payload,
    )

    answer = final_state.get("markdown_content", "") or final_state.get("summary", "")
    final_response = final_state.get("final_response")
    if not answer and isinstance(final_response, dict):
        answer = final_response.get("answer", "")

    return {
        "answer": answer,
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


async def run_ablation(
    benchmark: list[dict],
    config_name: str,
    config: dict,
    raw_output_path: Path | None = None,
    run_metadata: dict | None = None,
) -> dict:
    """Run entire benchmark under a single ablation config with incremental checkpointing."""
    cached_results_map = {}
    if raw_output_path and raw_output_path.exists():
        try:
            with open(raw_output_path, encoding="utf-8") as f:
                existing_data = json.load(f)
                for res_item in existing_data.get("results", []):
                    output = res_item.get("output", {})
                    if (
                        res_item.get("id")
                        and not output.get("skipped")
                        and output.get("answer")
                    ):
                        cached_results_map[res_item["id"]] = res_item
            if cached_results_map:
                logger.info(
                    "Found checkpoint for %s: %d/%d items already completed",
                    config_name,
                    len(cached_results_map),
                    len(benchmark),
                )
        except Exception as exc:
            logger.warning(
                "Could not load existing checkpoint from %s: %s", raw_output_path, exc
            )

    results = []

    for i, item in enumerate(benchmark):
        category = item.get("category", "")
        if category == "clarification":
            continue

        item_id = item["id"]
        question = item["question"]
        mode = item.get("mode", "quick_qa")

        # Resume from checkpoint if item was already answered successfully
        if item_id in cached_results_map:
            logger.info(
                "  [%d/%d] %s (mode=%s) -> Loaded from checkpoint",
                i + 1,
                len(benchmark),
                item_id,
                mode,
            )
            results.append(cached_results_map[item_id])
            continue

        doc_ids = item.get("request", {}).get("document_ids", [])
        doc_ids = [d for d in doc_ids if d and not d.startswith("<")]
        matter_id = item.get("request", {}).get("matter_id")

        logger.info("  [%d/%d] %s (mode=%s)", i + 1, len(benchmark), item_id, mode)

        if i > 0:
            await asyncio.sleep(4)

        try:
            output = await run_single_query(question, config, mode, doc_ids, matter_id)
            res_entry = {
                "id": item_id,
                "category": category,
                "mode": mode,
                "question": question,
                "output": output,
                "ground_truth": item["ground_truth_answer"],
            }
            results.append(res_entry)
        except AblationConfigurationError:
            raise
        except Exception as e:
            logger.error("  ✗ %s: %s", item_id, e)
            res_entry = {
                "id": item_id,
                "category": category,
                "mode": mode,
                "question": question,
                "output": {"answer": "", "skipped": True, "error": str(e)},
                "ground_truth": item["ground_truth_answer"],
            }
            results.append(res_entry)

        # Save checkpoint to disk after every single query execution
        if raw_output_path:
            intermediate_result = {
                "config_name": config_name,
                "description": config.get("description", ""),
                "total": len(results),
                "skipped": sum(1 for r in results if r["output"].get("skipped")),
                "results": results,
            }
            if run_metadata:
                intermediate_result["run_metadata"] = run_metadata
            with open(raw_output_path, "w", encoding="utf-8") as f:
                json.dump(intermediate_result, f, indent=2, default=str)

    res_final = {
        "config_name": config_name,
        "description": config.get("description", ""),
        "total": len(results),
        "skipped": sum(1 for r in results if r["output"].get("skipped")),
        "results": results,
    }
    if run_metadata:
        res_final["run_metadata"] = run_metadata
    return res_final


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
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output root (a benchmark-fingerprinted study directory is created)",
    )
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
    identity = benchmark_identity(benchmark, benchmark_path)
    install_gemini_rate_limiter()

    output_root = (
        Path(args.output) if args.output else BACKEND_DIR / "benchmarks" / "results"
    )
    output_dir = output_root / study_directory_name(identity)
    output_dir.mkdir(parents=True, exist_ok=True)

    configs_to_run = args.configs or list(ABLATION_CONFIGS.keys())
    unknown_configs = [name for name in configs_to_run if name not in ABLATION_CONFIGS]
    if unknown_configs:
        raise SystemExit(f"Unknown ablation config(s): {', '.join(unknown_configs)}")

    retrieval_effects_by_config = {}
    for config_name in configs_to_run:
        try:
            retrieval_effects_by_config[config_name] = preflight_ablation_config(
                ABLATION_CONFIGS[config_name]
            )
        except Exception as exc:
            raise SystemExit(
                f"Ablation preflight failed for '{config_name}': {exc}"
            ) from exc

    mode_counts = {
        mode: sum(1 for item in benchmark if item.get("mode") == mode)
        for mode in TARGET_MODES
    }
    print(
        f"Loaded balanced subset from {benchmark_path.name}: {len(benchmark)} entries"
    )
    print(f"Benchmark fingerprint: {identity['sha256']}")
    print(f"Study output: {output_dir}")
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
    for name in configs_to_run:
        print(
            f"  {name}: "
            f"{json.dumps(retrieval_effects_by_config[name], sort_keys=True)}"
        )
    print()

    all_results = {}

    for config_name in configs_to_run:
        config = ABLATION_CONFIGS[config_name]
        run_metadata = build_run_metadata(
            identity=identity,
            config_name=config_name,
            config=config,
            retrieval_effects=retrieval_effects_by_config[config_name],
        )
        raw_output_path = output_dir / f"ablation_{config_name}_raw.json"
        final_output_path = output_dir / f"ablation_{config_name}.json"
        failed_output_path = output_dir / f"ablation_{config_name}_metrics_failed.json"

        result = None

        # Fast check: skip if final evaluated output already exists and is complete
        if final_output_path.exists() and not args.collect_only:
            try:
                with open(final_output_path, encoding="utf-8") as f:
                    cached_final = json.load(f)
                validate_cached_result(cached_final, run_metadata)
                if cached_final.get("metric_status", {}).get("status") == "complete":
                    print(
                        f"\nFound complete results for {config_name} "
                        f"({cached_final.get('total', 0)} items evaluated): skipping."
                    )
                    all_results[config_name] = cached_final
                    continue
            except Exception as exc:
                logger.warning(
                    "Cached final result for %s invalid or incomplete: %s",
                    config_name,
                    exc,
                )

        # Phase 1: Collection
        if args.cached:
            # Skip collection, load from raw cache
            if not raw_output_path.exists():
                raise SystemExit(
                    f"Raw cache file not found: {raw_output_path}. "
                    "Cannot run --cached for this benchmark fingerprint."
                )
            print(f"\nLoading cached raw results for: {config_name}")
            with open(raw_output_path, encoding="utf-8") as f:
                result = json.load(f)
            try:
                validate_cached_result(result, run_metadata)
            except ValueError as exc:
                raise SystemExit(
                    f"Rejected incompatible cache {raw_output_path}: {exc}"
                ) from exc
        else:
            # Perform collection
            print(f"\n{'='*50}")
            print(f"Running: {config_name} — {config.get('description', '')}")
            print(f"{'='*50}")
            result = asyncio.run(
                run_ablation(
                    benchmark,
                    config_name,
                    config,
                    raw_output_path=raw_output_path,
                    run_metadata=run_metadata,
                )
            )
            result["run_metadata"] = run_metadata

            # Save raw result cache
            with open(raw_output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"  Saved raw cache: {raw_output_path.name}")

        # Phase 2: Evaluation
        if result is not None:
            if not args.skip_metrics and not args.collect_only:
                print("  Scoring metrics with shared Gemini rate limiter...")
                try:
                    result = add_quality_metrics(result)
                except MetricEvaluationError as exc:
                    with open(raw_output_path, "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2, default=str)
                    with open(failed_output_path, "w", encoding="utf-8") as f:
                        json.dump(result, f, indent=2, default=str)
                    raise SystemExit(
                        f"{exc}. Diagnostic output: {failed_output_path}\n"
                        "To resume after updating your GOOGLE_API_KEY, re-run the same command."
                    ) from exc

                # Save final results
                with open(final_output_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, default=str)
                # A successful retry supersedes any prior failed diagnostic for
                # this exact benchmark/configuration cache namespace.
                failed_output_path.unlink(missing_ok=True)
                print(f"  Saved final: {final_output_path.name}")

            all_results[config_name] = result

    # Only generate comparison if metrics are not skipped/collect-only
    if not args.skip_metrics and not args.collect_only:
        # Save comparison summary
        comparison = {
            "run_metadata": {
                "cache_schema_version": CACHE_SCHEMA_VERSION,
                "benchmark": identity,
                "evaluation_model": GEMINI_MODEL_NAME,
            },
            "configs": list(all_results.keys()),
            "config_metadata": {
                name: result.get("run_metadata", {})
                for name, result in all_results.items()
            },
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
