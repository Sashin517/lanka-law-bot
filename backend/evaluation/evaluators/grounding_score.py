"""Grounding score evaluator.

Reports the **continuous** grounding score (0.0 – 1.0) instead of a binary
pass/fail. The binary approach lost too much information and caused
false negatives when the LLM error fallback score (0.5) fell just below
a strict threshold (0.8).

Also annotates when the score was an auto-pass (e.g. drafting mode) vs
a genuine grounding verification result, so downstream analysis can
distinguish inflated scores from real ones.
"""


def grounding_score_evaluator(run, example):
    """Continuous 0.0-1.0 grounding quality score."""
    category = example.outputs.get("category", "")

    if category == "clarification":
        return {"key": "grounding_pass", "score": None, "comment": "Skipped for clarification"}

    # Try to get grounding score from the response metadata
    actual_score = run.outputs.get("grounding_score", None)

    # Detect auto-pass: drafting mode gets grounding_score=1.0 automatically
    # from grounding_node.py. We report the score but annotate it.
    route_data = run.outputs.get("route", {})
    is_drafting = route_data.get("route", "") == "drafting"

    if actual_score is not None:
        # Coerce to float in case of string serialization
        try:
            actual_score = float(actual_score)
        except (TypeError, ValueError):
            actual_score = None

    if actual_score is None:
        # Fallback: check if analysis claims exist and use citation coverage as proxy
        analysis = run.outputs.get("analysis", [])
        if analysis:
            cited = sum(1 for c in analysis if c.get("citation_ids"))
            actual_score = cited / len(analysis) if analysis else 0.0
        else:
            return {
                "key": "grounding_pass",
                "score": None,
                "comment": "No grounding score or analysis available",
            }

    # Clamp to valid range
    actual_score = max(0.0, min(1.0, actual_score))

    # Report continuous score instead of binary threshold check
    comment = f"score={actual_score:.2f}"
    if is_drafting:
        comment += " (auto-pass: drafting mode)"

    return {
        "key": "grounding_pass",
        "score": actual_score,
        "comment": comment,
    }
