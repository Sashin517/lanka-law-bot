"""Clarification accuracy evaluator.

Checks whether the system correctly identified that clarification is needed
(e.g., missing document for review, ambiguous query).
Applies to all entries but is most meaningful for clarification-category ones.
"""


def clarification_accuracy_evaluator(run, example):
    """Binary score: did the system correctly detect (or not detect) the need for clarification?"""
    expected_needs = example.outputs.get("expected_needs_clarification", False)

    route_data = run.outputs.get("route", {})
    actual_needs = route_data.get("needs_clarification", False)

    # Also check via the run output directly (some responses indicate clarification
    # by returning a clarification question in the answer)
    if not actual_needs:
        actual_needs = run.outputs.get("needs_clarification", False)

    match = expected_needs == actual_needs

    return {
        "key": "clarification_accuracy",
        "score": 1.0 if match else 0.0,
        "comment": f"expected_clarification={expected_needs} actual={actual_needs}",
    }
