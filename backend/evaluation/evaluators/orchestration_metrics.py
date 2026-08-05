"""Orchestration metrics — deterministic evaluators for multi-agent pipeline quality.

These metrics evaluate the supervisor's orchestration effectiveness
without requiring LLM calls (purely deterministic/computational).

Metrics:
- ``grounding_pass_rate``: Fraction of agent steps passing grounding on first attempt
- ``planning_appropriateness``: Did the supervisor correctly classify complexity?
- ``source_diversity``: Count of unique acts/sections in retrieved sources
- ``latency_metrics``: End-to-end and planning latency measurements
- ``orchestration_overhead_pct``: Planning time as percentage of total E2E time

Provides both standalone functions (for backend_comparison.py) and
LangSmith-compatible evaluator wrappers (for run_evaluation.py).
"""

from __future__ import annotations


# ── Default expected plan types per mode (shared with plan_accuracy) ──
_DEFAULT_EXPECTED_PLAN_TYPE: dict[str, str] = {
    "quick_qa": "fast_path",
    "deep_research": "planned",
    "drafting": "fast_path",
    "review": "fast_path",
    "reasoning": "planned",
}


def grounding_pass_rate(
    grounding_score: float,
    retry_count: int,
) -> dict:
    """Evaluate whether the grounding verifier passed on first attempt.

    Parameters
    ----------
    grounding_score : float
        The final grounding score from the pipeline.
    retry_count : int
        The number of grounding retries that occurred.

    Returns
    -------
    dict
        Keys: ``first_pass``, ``grounding_score``, ``retry_count``.
    """
    first_pass = retry_count == 0 and grounding_score >= 0.5

    return {
        "first_pass": 1.0 if first_pass else 0.0,
        "grounding_score": grounding_score,
        "retry_count": retry_count,
    }


def planning_appropriateness(
    execution_trace: dict,
    expected_plan_type: str,
) -> dict:
    """Evaluate whether the supervisor correctly classified query complexity.

    Parameters
    ----------
    execution_trace : dict
        The execution trace from the pipeline's final response.
    expected_plan_type : str
        Either ``"fast_path"`` or ``"planned"``.

    Returns
    -------
    dict
        Keys: ``appropriate``, ``expected``, ``actual``.
    """
    actual_plan_type = execution_trace.get("plan_type", "fast_path")
    match = actual_plan_type == expected_plan_type

    return {
        "appropriate": 1.0 if match else 0.0,
        "expected": expected_plan_type,
        "actual": actual_plan_type,
    }


def source_diversity(sources: list[dict]) -> dict:
    """Measure diversity of retrieved legal sources.

    Counts unique act titles and unique sections to measure how
    broadly the retrieval system covered the legal landscape.

    Parameters
    ----------
    sources : list[dict]
        The retrieved sources from the pipeline output.

    Returns
    -------
    dict
        Keys: ``unique_acts``, ``unique_sections``, ``total_sources``,
        ``act_names``.
    """
    act_titles: set[str] = set()
    sections: set[str] = set()

    for src in sources:
        title = src.get("title", "").strip()
        section = src.get("section", "").strip()

        if title:
            act_titles.add(title.lower())
        if section:
            sections.add(f"{title}:{section}".lower())

    return {
        "unique_acts": len(act_titles),
        "unique_sections": len(sections),
        "total_sources": len(sources),
        "act_names": sorted(act_titles),
    }


def latency_metrics(
    e2e_seconds: float,
    planning_seconds: float | None = None,
) -> dict:
    """Package latency measurements.

    Parameters
    ----------
    e2e_seconds : float
        End-to-end pipeline execution time in seconds.
    planning_seconds : float | None
        Time spent in supervisor planning (if captured).

    Returns
    -------
    dict
        Keys: ``e2e_ms``, ``planning_ms``, ``planning_overhead_pct``.
    """
    e2e_ms = round(e2e_seconds * 1000, 1)
    planning_ms = round((planning_seconds or 0) * 1000, 1)
    overhead_pct = round(
        (planning_ms / e2e_ms * 100) if e2e_ms > 0 else 0, 1
    )

    return {
        "e2e_ms": e2e_ms,
        "planning_ms": planning_ms,
        "planning_overhead_pct": overhead_pct,
    }


# ── LangSmith-compatible evaluator wrappers ────────────────────────


def planning_appropriateness_langsmith_evaluator(run, example):
    """LangSmith evaluator wrapper for planning appropriateness.

    Checks whether the supervisor used the right plan type (fast_path vs
    planned) for the given query mode.  Infers expected plan type from
    the query mode if not annotated in the benchmark.
    """
    category = example.outputs.get("category", "")
    if category == "clarification":
        return {"key": "planning_appropriateness", "score": None, "comment": "Skipped for clarification"}

    execution_trace = run.outputs.get("execution_trace", {})
    mode = example.inputs.get("mode", "quick_qa")

    # Use annotated expected type if available, otherwise infer from mode
    expected_plan_type = example.outputs.get(
        "expected_plan_type",
        _DEFAULT_EXPECTED_PLAN_TYPE.get(mode, "fast_path"),
    )

    result = planning_appropriateness(execution_trace, expected_plan_type)

    return {
        "key": "planning_appropriateness",
        "score": result["appropriate"],
        "comment": f"expected={result['expected']} actual={result['actual']}",
    }


def orchestration_overhead_langsmith_evaluator(run, example):
    """LangSmith evaluator wrapper for orchestration overhead percentage.

    Reports the planning overhead as a fraction of total E2E time.
    Reads ``planning_seconds`` from the execution trace (instrumented
    in the router node).

    Score is inverted: lower overhead → higher score (closer to 1.0).
    Score = 1.0 - (overhead_pct / 100), clamped to [0.0, 1.0].
    """
    category = example.outputs.get("category", "")
    if category == "clarification":
        return {"key": "orchestration_overhead_pct", "score": None, "comment": "Skipped for clarification"}

    execution_trace = run.outputs.get("execution_trace", {})
    planning_seconds = execution_trace.get("planning_seconds")
    e2e_seconds = execution_trace.get("e2e_seconds", 0)

    if planning_seconds is None or e2e_seconds <= 0:
        return {
            "key": "orchestration_overhead_pct",
            "score": None,
            "comment": "No timing data available",
        }

    result = latency_metrics(e2e_seconds, planning_seconds)
    overhead_pct = result["planning_overhead_pct"]

    # Invert: lower overhead → higher score (more efficient)
    score = max(0.0, min(1.0, 1.0 - overhead_pct / 100.0))

    return {
        "key": "orchestration_overhead_pct",
        "score": score,
        "comment": f"planning={result['planning_ms']:.0f}ms e2e={result['e2e_ms']:.0f}ms overhead={overhead_pct:.1f}%",
    }
