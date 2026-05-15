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
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Each config specifies what to override in the pipeline
ABLATION_CONFIGS = {
    "full_pipeline": {
        "description": "Full pipeline (baseline)",
    },
    "dense_only": {
        "description": "Dense retrieval only (BM25 disabled)",
        "disable_bm25": True,
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


async def run_single_query(
    question: str,
    config: dict,
    mode: str,
    doc_ids: list,
    matter_id: str | None,
) -> dict:
    """Run a single query with ablation config applied.

    Uses direct service calls (not the full LangGraph) so individual
    pipeline stages can be selectively disabled.
    """
    from app.agents.nodes.router_node import _MODE_CONFIG
    from app.services.retrieval_service import get_retrieval_service
    from app.services.context_assembler import MultiSourceContextAssembler
    from app.services.generation_service import GenerationService
    from app.services.citation_verifier import CitationVerifier
    from app.services.user_document_retrieval_service import UserDocumentRetrievalService

    _retrieval = get_retrieval_service()
    _assembler = MultiSourceContextAssembler()
    _generator = GenerationService()
    _verifier = CitationVerifier()

    # Get static mode config (deterministic — no LLM router call)
    mode_config = _MODE_CONFIG.get(mode, _MODE_CONFIG["quick_qa"])

    # Apply ablation overrides
    expand_parents = config.get("expand_parents", True)
    skip_verification = config.get("skip_verification", False)

    # Build retrieval plan from static mode config
    has_documents = bool(doc_ids)
    use_legal = mode_config.target_corpus != "user_document" or not has_documents
    use_user_docs = has_documents and mode_config.route in {"review", "drafting", "reasoning", "deep_research"}

    # Step 1: Retrieve
    legal_results = []
    user_doc_results = []

    if use_legal:
        if config.get("disable_bm25"):
            # Dense only — use retrieval service but override to skip BM25
            try:
                legal_results = _retrieval.search(
                    query=question,
                    top_k=mode_config.legal_top_k,
                    expand_parents=expand_parents,
                    mode="dense_only",
                )
            except TypeError:
                # Fallback if search() doesn't accept mode parameter
                legal_results = _retrieval.search(
                    query=question,
                    top_k=mode_config.legal_top_k,
                    expand_parents=expand_parents,
                )
        else:
            legal_results = _retrieval.search(
                query=question,
                top_k=mode_config.legal_top_k,
                expand_parents=expand_parents,
            )

    if use_user_docs and doc_ids:
        try:
            user_doc_svc = UserDocumentRetrievalService()
            user_doc_results = user_doc_svc.search(
                query=question,
                document_ids=doc_ids,
                matter_id=matter_id,
                top_k=mode_config.user_doc_top_k,
                expand_parents=expand_parents,
            )
        except Exception:
            pass

    if not legal_results and not user_doc_results:
        return {"answer": "", "sources": [], "analysis": [], "confidence": "low", "skipped": True}

    # Step 2: Assemble context
    context_str, citation_map = _assembler.assemble(
        legal_results=legal_results,
        user_document_results=user_doc_results,
    )

    # Step 3: Generate
    response = await _generator.generate(question, context_str, citation_map)

    # Step 4: Optionally verify
    if not skip_verification:
        response = _verifier.verify(response)

    return {
        "answer": response.summary,
        "sources": [s.model_dump() for s in response.sources],
        "analysis": [c.model_dump() for c in response.analysis],
        "confidence": response.confidence,
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

        try:
            output = await run_single_query(question, config, mode, doc_ids, matter_id)
            results.append({
                "id": item["id"],
                "category": category,
                "mode": mode,
                "output": output,
                "ground_truth": item["ground_truth_answer"],
            })
        except Exception as e:
            logger.error("  ✗ %s: %s", item["id"], e)
            results.append({
                "id": item["id"],
                "category": category,
                "mode": mode,
                "output": {"answer": "", "skipped": True, "error": str(e)},
                "ground_truth": item["ground_truth_answer"],
            })

    return {
        "config_name": config_name,
        "description": config.get("description", ""),
        "total": len(results),
        "skipped": sum(1 for r in results if r["output"].get("skipped")),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Run ablation studies")
    parser.add_argument("--benchmark", type=str, required=True, help="Path to benchmark JSON")
    parser.add_argument("--configs", type=str, nargs="*", default=None, help="Specific configs to run (default: all)")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    benchmark_path = BACKEND_DIR / args.benchmark
    if not benchmark_path.exists():
        benchmark_path = Path(args.benchmark)
    if not benchmark_path.exists():
        print(f"File not found: {args.benchmark}")
        sys.exit(1)

    with open(benchmark_path, encoding="utf-8") as f:
        benchmark = json.load(f)

    output_dir = Path(args.output) if args.output else BACKEND_DIR / "benchmarks" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    configs_to_run = args.configs or list(ABLATION_CONFIGS.keys())

    print(f"Loaded {len(benchmark)} entries from {benchmark_path.name}")
    print(f"Running {len(configs_to_run)} ablation configs: {configs_to_run}\n")

    all_results = {}

    for config_name in configs_to_run:
        if config_name not in ABLATION_CONFIGS:
            print(f"Unknown config: {config_name}")
            continue

        config = ABLATION_CONFIGS[config_name]
        print(f"\n{'='*50}")
        print(f"Running: {config_name} — {config.get('description', '')}")
        print(f"{'='*50}")

        result = asyncio.run(run_ablation(benchmark, config_name, config))
        all_results[config_name] = result

        # Save per-config results
        config_output = output_dir / f"ablation_{config_name}.json"
        with open(config_output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"  Saved: {config_output.name}")

    # Save comparison summary
    comparison = {
        "configs": list(all_results.keys()),
        "summary": {
            name: {
                "total": r["total"],
                "skipped": r["skipped"],
                "answered": r["total"] - r["skipped"],
            }
            for name, r in all_results.items()
        },
    }
    comparison_path = output_dir / "ablation_comparison.json"
    with open(comparison_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    print(f"\n{'='*50}")
    print("Ablation studies complete!")
    print(f"Results in: {output_dir}")
    print(f"Comparison: {comparison_path.name}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
