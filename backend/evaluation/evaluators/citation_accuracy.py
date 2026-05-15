"""Citation accuracy evaluator.

Computes F1 score between expected and actual source titles in the response.
Skips clarification entries (which expect no sources).
"""


def citation_accuracy_evaluator(run, example):
    """F1 score of expected vs actual source titles."""
    category = example.outputs.get("category", "")

    if category == "clarification":
        return {"key": "citation_f1", "score": None, "comment": "Skipped for clarification"}

    expected_sources = example.outputs.get("expected_sources", [])
    if not expected_sources:
        return {"key": "citation_f1", "score": None, "comment": "No expected sources defined"}

    actual_sources = run.outputs.get("sources", [])

    # Normalize titles for comparison (lowercase, strip whitespace)
    expected_titles = {s.get("title", "").lower().strip() for s in expected_sources}
    actual_titles = {s.get("title", "").lower().strip() for s in actual_sources}

    # Remove empty strings
    expected_titles.discard("")
    actual_titles.discard("")

    if not expected_titles:
        return {"key": "citation_f1", "score": None, "comment": "No expected titles"}

    overlap = expected_titles & actual_titles
    precision = len(overlap) / len(actual_titles) if actual_titles else 0.0
    recall = len(overlap) / len(expected_titles) if expected_titles else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "key": "citation_f1",
        "score": f1,
        "comment": f"P={precision:.2f} R={recall:.2f} | expected={list(expected_titles)} actual={list(actual_titles)}",
    }
