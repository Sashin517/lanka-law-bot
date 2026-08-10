"""Main evaluation harness — runs the LankaLawBot pipeline against a LangSmith dataset.

Uses the LangGraph-based pipeline (same path as POST /api/search in production).
Each benchmark entry's ``mode`` field is passed to the graph so routing is
deterministic — exactly matching the production frontend behavior.

Registers **all** evaluators (correctness, citation, clarification, grounding,
plan accuracy, goal accuracy, planning appropriateness, orchestration overhead)
so every metric column in the exported CSV is properly populated.

Usage:
    cd backend
    python -m evaluation.run_evaluation --dataset "sllb-v1" --prefix "full-pipeline-v1"
"""

import argparse
import asyncio
import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from langsmith.evaluation import evaluate

from evaluation.evaluators.correctness import correctness_evaluator
from evaluation.evaluators.citation_accuracy import citation_accuracy_evaluator
from evaluation.evaluators.clarification_accuracy import clarification_accuracy_evaluator
from evaluation.evaluators.grounding_score import grounding_score_evaluator
from evaluation.evaluators.plan_accuracy import plan_accuracy_langsmith_evaluator
from evaluation.evaluators.agent_goal_accuracy import agent_goal_accuracy_langsmith_evaluator
from evaluation.evaluators.orchestration_metrics import (
    planning_appropriateness_langsmith_evaluator,
    orchestration_overhead_langsmith_evaluator,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


async def _run_pipeline(
    question: str,
    mode: str,
    document_ids: list,
    matter_id: str | None,
) -> dict:
    """Run the full LankaLawBot pipeline via LangGraph and return structured output."""
    from evaluation.eval_pipeline import run_pipeline

    start_time = time.monotonic()

    final_state = await run_pipeline(
        question=question,
        mode=mode,
        document_ids=document_ids,
        matter_id=matter_id,
    )

    e2e_seconds = time.monotonic() - start_time

    # Return the API-ready response if formatter produced it
    if final_state.get("final_response"):
        result = final_state["final_response"]
        # Inject E2E timing into execution_trace for the overhead evaluator
        if "execution_trace" in result:
            result["execution_trace"]["e2e_seconds"] = e2e_seconds
        return result

    # Fallback: build response from raw state fields
    return {
        "answer": final_state.get("summary", ""),
        "markdown_content": final_state.get("markdown_content", ""),
        "analysis": [
            c.model_dump() if hasattr(c, "model_dump") else c
            for c in final_state.get("analysis", [])
        ],
        "sources": [
            s.model_dump() if hasattr(s, "model_dump") else s
            for s in final_state.get("retrieved_sources", [])
        ],
        "confidence": final_state.get("confidence", "low"),
        "grounding_score": (
            final_state.get("grounding", {}).get("grounding_score", 0.0)
            if isinstance(final_state.get("grounding"), dict)
            else getattr(final_state.get("grounding"), "grounding_score", 0.0)
        ),
        "route": {
            "route": final_state.get("route", ""),
            "task_type": final_state.get("task_type", ""),
            "answer_mode": final_state.get("answer_mode", ""),
            "target_corpus": final_state.get("target_corpus", ""),
            "confidence": final_state.get("route_confidence", "medium"),
            "needs_clarification": final_state.get("needs_clarification", False),
            "clarification_question": final_state.get("clarification_question"),
        },
        "needs_clarification": final_state.get("needs_clarification", False),
        "execution_trace": {
            "plan_type": (
                final_state.get("execution_plan", {}).get("plan_type", "fast_path")
                if isinstance(final_state.get("execution_plan"), dict)
                else getattr(final_state.get("execution_plan"), "plan_type", "fast_path")
            ),
            "steps_executed": [],
            "total_steps": 0,
            "completed_agents": final_state.get("completed_agents", []),
            "planning_seconds": final_state.get("planning_seconds", 0.0),
            "e2e_seconds": e2e_seconds,
        },
    }


def target_function(inputs: dict) -> dict:
    """LangSmith target — wraps async pipeline in sync call."""
    question = inputs.get("question", "")
    mode = inputs.get("mode", "quick_qa")
    document_ids = inputs.get("document_ids", [])
    matter_id = inputs.get("matter_id")

    # Filter out placeholder document IDs
    document_ids = [d for d in document_ids if d and not d.startswith("<")]

    # Throttle to stay under Gemini free-tier rate limits (~15 RPM).
    # Each question uses ~2-5 LLM calls (router + worker + grounding).
    # Then evaluators add ~2 more (correctness + goal_accuracy).
    time.sleep(15)

    try:
        result = asyncio.run(
            _run_pipeline(question, mode, document_ids, matter_id)
        )
    except Exception as e:
        logger.error("Pipeline failed for question: '%s' — %s", question[:80], e)
        result = {
            "answer": f"ERROR: {e}",
            "markdown_content": "",
            "analysis": [],
            "sources": [],
            "confidence": "low",
            "grounding_score": 0.0,
            "route": {},
            "needs_clarification": False,
            "execution_trace": {
                "plan_type": "fast_path",
                "steps_executed": [],
                "total_steps": 0,
                "completed_agents": [],
                "planning_seconds": 0.0,
                "e2e_seconds": 0.0,
            },
        }

    return result


def main():
    parser = argparse.ArgumentParser(description="Run LankaLawBot evaluation")
    parser.add_argument("--dataset", type=str, required=True, help="LangSmith dataset name")
    parser.add_argument("--prefix", type=str, default="eval", help="Experiment prefix")
    parser.add_argument("--max-concurrency", type=int, default=1, help="Max concurrent evaluations (keep at 1 for free-tier API)")
    parser.add_argument("--no-throttle", action="store_true", help="Disable rate-limit throttle (for paid API tiers)")
    args = parser.parse_args()

    print(f"Starting evaluation on dataset: '{args.dataset}'")
    print(f"Experiment prefix: '{args.prefix}'")
    print(f"Max concurrency: {args.max_concurrency}")
    print(f"Evaluators: correctness, citation_f1, clarification_accuracy, grounding_pass,")
    print(f"            plan_accuracy, agent_goal_accuracy, planning_appropriateness,")
    print(f"            orchestration_overhead_pct")
    print()

    results = evaluate(
        target_function,
        data=args.dataset,
        evaluators=[
            # ── RAG quality metrics ──
            correctness_evaluator,
            citation_accuracy_evaluator,
            clarification_accuracy_evaluator,
            grounding_score_evaluator,
            # ── Multi-agent orchestration metrics ──
            plan_accuracy_langsmith_evaluator,
            agent_goal_accuracy_langsmith_evaluator,
            planning_appropriateness_langsmith_evaluator,
            orchestration_overhead_langsmith_evaluator,
        ],
        experiment_prefix=args.prefix,
        max_concurrency=args.max_concurrency,
    )

    print("\n" + "=" * 60)
    print("Evaluation complete!")
    print(f"View results at: https://smith.langchain.com/")
    print("=" * 60)


if __name__ == "__main__":
    main()
