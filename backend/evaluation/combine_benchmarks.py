"""Merge per-category benchmark JSONs into a single full_benchmark.json.

Usage:
    cd backend
    python -m evaluation.combine_benchmarks
"""

import json
import sys
from collections import Counter
from pathlib import Path

DATASETS_DIR = Path(__file__).resolve().parent.parent / "benchmarks" / "datasets"

CATEGORY_FILES = [
    "quick_qa.json",
    "deep_research.json",
    "reasoning.json",
    "drafting.json",
    "review.json",
    "verify.json",
    "clarification.json",
]


VALID_MODES = {"quick_qa", "deep_research", "drafting", "review", "reasoning"}


def load_category(filepath: Path) -> list[dict]:
    if not filepath.exists():
        print(f"  [SKIP] {filepath.name} — not found")
        return []
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print(f"  [ERROR] {filepath.name} — expected a JSON array at top level")
        return []
    return data


def validate_ids(entries: list[dict]) -> list[str]:
    """Return list of duplicate IDs."""
    seen: dict[str, int] = Counter(e.get("id", "") for e in entries)
    return [k for k, v in seen.items() if v > 1]


def ensure_mode(entries: list[dict]) -> int:
    """Auto-derive ``mode`` from ``expected_route`` for entries missing it.

    Returns the count of entries that were patched.
    """
    patched = 0
    for entry in entries:
        if "mode" not in entry or entry["mode"] not in VALID_MODES:
            route = entry.get("expected_route", "quick_qa")
            entry["mode"] = route if route in VALID_MODES else "quick_qa"
            patched += 1
    return patched


def main():
    all_entries: list[dict] = []

    print("Combining benchmark datasets...\n")
    for filename in CATEGORY_FILES:
        entries = load_category(DATASETS_DIR / filename)
        if entries:
            print(f"  [OK]   {filename:30s} — {len(entries)} entries")
            all_entries.extend(entries)

    # Check for duplicate IDs
    dupes = validate_ids(all_entries)
    if dupes:
        print(f"\n  [WARN] Duplicate IDs found: {dupes}")

    # Ensure every entry has a valid 'mode' field
    mode_patched = ensure_mode(all_entries)
    if mode_patched:
        print(f"\n  [INFO] Auto-derived 'mode' for {mode_patched} entries")

    # Write combined file
    output_path = DATASETS_DIR / "full_benchmark.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, indent=2, ensure_ascii=False)

    # Print stats
    categories = Counter(e.get("category", "unknown") for e in all_entries)
    difficulties = Counter(e.get("difficulty", "unknown") for e in all_entries)
    modes = Counter(e.get("mode", "unknown") for e in all_entries)
    fixture_count = sum(1 for e in all_entries if e.get("requires_user_document"))

    print(f"\n{'='*50}")
    print(f"Total entries: {len(all_entries)}")
    print(f"Output:        {output_path}")
    print(f"\nBy category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat:25s} {count}")
    print(f"\nBy mode:")
    for mode, count in sorted(modes.items()):
        print(f"  {mode:25s} {count}")
    print(f"\nBy difficulty:")
    for diff, count in sorted(difficulties.items()):
        print(f"  {diff:25s} {count}")
    print(f"\nRequire fixture documents: {fixture_count}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
