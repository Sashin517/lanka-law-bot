"""Grounding score evaluator.

Reports the **continuous** grounding score (0.0 – 1.0) instead of a binary
pass/fail. The binary approach lost too much information and caused
false negatives when the LLM error fallback score (0.5) fell just below
a strict threshold (0.8).

Drafting responses use the same grounding judge as other response modes, so
their scores are reported without mode-specific adjustment.
"""


def grounding_score_evaluator(run, example):
    """Continuous 0.0-1.0 grounding quality score."""
    category = example.outputs.get("category", "")

    if category == "clarification":
        return {"key": "grounding_pass", "score": None, "comment": "Skipped for clarification"}

    # Try to get grounding score from the response metadata
    actual_score = run.outputs.get("grounding_score", None)

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

    return {
        "key": "grounding_pass",
        "score": actual_score,
        "comment": comment,
    }
