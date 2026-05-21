"""Grounding score evaluator.

Checks if the system's grounding score meets the minimum threshold
defined in the benchmark entry. Skips clarification entries.
"""


def grounding_score_evaluator(run, example):
    """Binary: does grounding score meet the expected minimum?"""
    category = example.outputs.get("category", "")

    if category == "clarification":
        return {"key": "grounding_pass", "score": None, "comment": "Skipped for clarification"}

    min_threshold = example.outputs.get("expected_grounding_min", 0.7)

    # Try to get grounding score from the route or response data
    route_data = run.outputs.get("route", {})
    # The grounding score may be in the response metadata
    actual_score = run.outputs.get("grounding_score", None)

    if actual_score is None:
        # If grounding_score is not directly available, check if analysis
        # claims exist (presence of grounded claims indicates grounding ran)
        analysis = run.outputs.get("analysis", [])
        if analysis:
            # Use citation coverage as a proxy: proportion of claims with citations
            cited = sum(1 for c in analysis if c.get("citation_ids"))
            actual_score = cited / len(analysis) if analysis else 0.0
        else:
            return {
                "key": "grounding_pass",
                "score": None,
                "comment": "No grounding score or analysis available",
            }

    passes = actual_score >= min_threshold

    return {
        "key": "grounding_pass",
        "score": 1.0 if passes else 0.0,
        "comment": f"score={actual_score:.2f} threshold={min_threshold}",
    }
