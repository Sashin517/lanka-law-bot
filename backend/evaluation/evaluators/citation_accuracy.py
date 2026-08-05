"""Citation accuracy evaluator.

Computes F1 score between expected and actual source titles in the response.
Skips clarification entries (which expect no sources).

Uses fuzzy canonical matching to handle the common mismatch between
benchmark titles (e.g. 'Electronic Transactions Act, No. 19 of 2006')
and pipeline titles (e.g. 'Electronic-Transactions-Consolidated-2024').
"""

import re


def _canonicalize_title(title: str) -> str:
    """Reduce a legal source title to a canonical matchable form.

    Strips:
    - Act/Ordinance number suffixes (', No. 19 of 2006')
    - Consolidated year suffixes ('Consolidated-2024', 'Consolidated 2024')
    - Amendment markers ('(Amendment)')
    - Punctuation, hyphens, underscores
    - Common filler words that vary between naming conventions

    Examples
    --------
    'Electronic Transactions Act, No. 19 of 2006'  → 'electronic transactions'
    'Electronic-Transactions-Consolidated-2024'     → 'electronic transactions'
    'Partition Law (Consolidated 2024)'             → 'partition'
    'Partition Law'                                 → 'partition'
    'Land Development Ordinance (Consolidated 2024)'→ 'land development'
    'Land-Development-Consolidated-2024.md'         → 'land development'
    """
    t = title.lower().strip()

    # Strip file extension
    t = re.sub(r'\.md$', '', t)

    # Strip consolidated year patterns
    t = re.sub(r'[-_ ]*\(?consolidated\)?[-_ ]*\d{4}', '', t)

    # Strip act/ordinance number: ', No. 19 of 2006' or 'No 6 of 2018'
    t = re.sub(r',?\s*no\.?\s*\d+\s*of\s*\d{4}', '', t)

    # Strip '(Amendment)' and similar parentheticals
    t = re.sub(r'\(amendment\)', '', t)
    t = re.sub(r'\(\s*\)', '', t)

    # Strip trailing legal type markers for cleaner core matching
    # but keep them for the initial comparison
    core = t

    # Replace hyphens and underscores with spaces
    core = core.replace('-', ' ').replace('_', ' ')

    # Strip filler words that vary between naming conventions
    core = re.sub(r'\b(the|of|and|in|to|for|with|by|on|at|as|or)\b', ' ', core)

    # Strip 'act', 'ordinance', 'law', 'regulation' from the end for core matching
    core = re.sub(r'\b(act|ordinance|law|regulation|rules|order)\b', '', core)

    # Collapse whitespace
    core = re.sub(r'\s+', ' ', core).strip()

    return core


def _titles_match(expected: str, actual: str) -> bool:
    """Check if two titles refer to the same legal source using canonical matching.

    Returns True if either:
    1. The canonical forms are identical, or
    2. One canonical form is a substring of the other (handles partial names)
    """
    ce = _canonicalize_title(expected)
    ca = _canonicalize_title(actual)

    if not ce or not ca:
        return False

    # Exact canonical match
    if ce == ca:
        return True

    # Substring match (handles 'trusts' matching 'trusts amendment')
    if ce in ca or ca in ce:
        return True

    return False


def citation_accuracy_evaluator(run, example):
    """F1 score of expected vs actual source titles (fuzzy matched)."""
    category = example.outputs.get("category", "")

    if category == "clarification":
        return {"key": "citation_f1", "score": None, "comment": "Skipped for clarification"}

    expected_sources = example.outputs.get("expected_sources", [])
    if not expected_sources:
        return {"key": "citation_f1", "score": None, "comment": "No expected sources defined"}

    actual_sources = run.outputs.get("sources", [])

    # Extract titles (using both 'title' and 'filename' fields from actual sources)
    expected_titles = [s.get("title", "").strip() for s in expected_sources]
    expected_titles = [t for t in expected_titles if t]

    actual_titles = []
    for s in actual_sources:
        title = s.get("title", "").strip()
        if title:
            actual_titles.append(title)
        # Also try filename as a fallback for matching
        fname = s.get("filename", "").strip()
        if fname and fname != title:
            actual_titles.append(fname)

    if not expected_titles:
        return {"key": "citation_f1", "score": None, "comment": "No expected titles"}

    if not actual_titles:
        return {
            "key": "citation_f1",
            "score": 0.0,
            "comment": f"No actual sources | expected={expected_titles}",
        }

    # Count matches using fuzzy canonical matching
    # Each expected title can match at most one actual title (greedy matching)
    matched_expected = 0
    matched_actual_indices: set[int] = set()

    for exp_title in expected_titles:
        for j, act_title in enumerate(actual_titles):
            if j not in matched_actual_indices and _titles_match(exp_title, act_title):
                matched_expected += 1
                matched_actual_indices.add(j)
                break

    # Deduplicate actual titles for precision calculation
    # (we may have added both title and filename for the same source)
    unique_actual_count = len({_canonicalize_title(t) for t in actual_titles})
    unique_actual_count = max(unique_actual_count, 1)

    precision = len(matched_actual_indices) / unique_actual_count
    recall = matched_expected / len(expected_titles)
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "key": "citation_f1",
        "score": f1,
        "comment": (
            f"P={precision:.2f} R={recall:.2f} matched={matched_expected}/{len(expected_titles)} | "
            f"expected={expected_titles} actual={actual_titles[:5]}"
        ),
    }
