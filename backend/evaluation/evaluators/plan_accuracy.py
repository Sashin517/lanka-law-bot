"""Plan accuracy evaluator — measures supervisor planning correctness.

Computes how well the supervisor's execution plan matches the expected
agent sequence annotated in the benchmark entry.

Metrics produced:
- ``plan_type_match``:  1.0 if plan_type matches expected, else 0.0
- ``agent_sequence_f1``: F1 score of expected vs actual agent list
- ``plan_accuracy``: weighted combination (0.4 * type + 0.6 * f1)

When ``expected_plan_type`` or ``expected_agents`` are not annotated in the
benchmark, the evaluator infers sensible defaults from the query ``mode``
so the metric is meaningful even without explicit annotations.

Provides both a standalone function (for backend_comparison.py) and a
LangSmith-compatible evaluator wrapper (for run_evaluation.py).
"""

from __future__ import annotations


# ── Default expected plan types and agents per mode ──
# Used when the benchmark entry does not contain explicit annotations.
_DEFAULT_PLAN_CONFIG: dict[str, dict] = {
    "quick_qa": {
        "expected_plan_type": "fast_path",
        "expected_agents": ["quick_qa"],
    },
    "deep_research": {
        "expected_plan_type": "planned",
        "expected_agents": ["deep_research"],
    },
    "drafting": {
        "expected_plan_type": "fast_path",
        "expected_agents": ["drafting"],
    },
    "review": {
        "expected_plan_type": "fast_path",
        "expected_agents": ["review"],
    },
    "reasoning": {
        "expected_plan_type": "planned",
        "expected_agents": ["reasoning"],
    },
}


def _f1_score(expected: list[str], actual: list[str]) -> float:
    """Compute F1 between two lists of agent names (order-insensitive)."""
    expected_set = set(expected)
    actual_set = set(actual)

    if not expected_set and not actual_set:
        return 1.0
    if not expected_set or not actual_set:
        return 0.0

    overlap = expected_set & actual_set
    precision = len(overlap) / len(actual_set)
    recall = len(overlap) / len(expected_set)

    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def plan_accuracy_evaluator(
    execution_trace: dict,
    benchmark_entry: dict,
) -> dict:
    """Evaluate supervisor planning accuracy.

    Parameters
    ----------
    execution_trace : dict
        The ``execution_trace`` from the pipeline's final response.
        Contains ``plan_type`` and ``steps_executed``.
    benchmark_entry : dict
        The benchmark entry with ``expected_plan_type`` and
        ``expected_agents``.

    Returns
    -------
    dict
        Keys: ``plan_type_match``, ``agent_sequence_f1``,
        ``plan_accuracy``, ``comment``.
    """
    expected_plan_type = benchmark_entry.get("expected_plan_type", "fast_path")
    expected_agents = benchmark_entry.get("expected_agents", [])

    actual_plan_type = execution_trace.get("plan_type", "fast_path")
    actual_steps = execution_trace.get("steps_executed", [])
    actual_agents = [
        step.get("agent", "") for step in actual_steps if step.get("agent")
    ]
    if not actual_agents:
        actual_agents = execution_trace.get("completed_agents", [])

    # 1. Plan type match
    plan_type_match = 1.0 if actual_plan_type == expected_plan_type else 0.0

    # 2. Agent sequence F1
    agent_f1 = _f1_score(expected_agents, actual_agents)

    # 3. Weighted combination
    plan_accuracy = 0.4 * plan_type_match + 0.6 * agent_f1

    return {
        "plan_type_match": plan_type_match,
        "agent_sequence_f1": agent_f1,
        "plan_accuracy": plan_accuracy,
        "comment": (
            f"expected_type={expected_plan_type} actual_type={actual_plan_type} | "
            f"expected_agents={expected_agents} actual_agents={actual_agents}"
        ),
    }


# ── LangSmith-compatible evaluator wrapper ──────────────────────────


def plan_accuracy_langsmith_evaluator(run, example):
    """LangSmith evaluator wrapper for plan accuracy.

    Extracts execution_trace from the run outputs and expected annotations
    from the example outputs.  When the benchmark lacks ``expected_plan_type``
    or ``expected_agents``, infers sensible defaults from the query mode.
    """
    category = example.outputs.get("category", "")
    if category == "clarification":
        return {"key": "plan_accuracy", "score": None, "comment": "Skipped for clarification"}

    execution_trace = run.outputs.get("execution_trace", {})

    # Build the benchmark entry for the evaluator.
    # If the benchmark has explicit annotations, use them.
    # Otherwise, infer from the query mode.
    mode = example.inputs.get("mode", "quick_qa")
    defaults = _DEFAULT_PLAN_CONFIG.get(mode, _DEFAULT_PLAN_CONFIG["quick_qa"])

    benchmark_entry = {
        "expected_plan_type": example.outputs.get(
            "expected_plan_type", defaults["expected_plan_type"]
        ),
        "expected_agents": example.outputs.get(
            "expected_agents", defaults["expected_agents"]
        ),
    }

    result = plan_accuracy_evaluator(execution_trace, benchmark_entry)

    return {
        "key": "plan_accuracy",
        "score": result["plan_accuracy"],
        "comment": result.get("comment", ""),
    }
