"""One-time script: add 'mode' field to all benchmark JSONs.

Maps expected_route → mode:
  quick_qa      → quick_qa
  deep_research → deep_research
  drafting      → drafting
  review        → review
  reasoning     → reasoning

Verify entries: expected_route is already "quick_qa", so mode = "quick_qa".
Clarification entries: derive from expected_route (e.g. "review" or "reasoning").

Run once:
    python -m evaluation._patch_benchmarks
"""

import json
from pathlib import Path

DATASETS_DIR = Path(__file__).resolve().parent.parent / "benchmarks" / "datasets"

FILES = [
    "quick_qa.json",
    "deep_research.json",
    "reasoning.json",
    "drafting.json",
    "review.json",
    "verify.json",
    "clarification.json",
]

VALID_MODES = {"quick_qa", "deep_research", "drafting", "review", "reasoning"}


def derive_mode(entry: dict) -> str:
    """Derive the mode from expected_route."""
    route = entry.get("expected_route", "quick_qa")
    if route in VALID_MODES:
        return route
    # Fallback for any unexpected values
    return "quick_qa"


def main():
    for filename in FILES:
        filepath = DATASETS_DIR / filename
        if not filepath.exists():
            print(f"  [SKIP] {filename} — not found")
            continue

        with open(filepath, encoding="utf-8") as f:
            entries = json.load(f)

        patched = 0
        for entry in entries:
            if "mode" not in entry:
                entry["mode"] = derive_mode(entry)
                patched += 1

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        print(f"  [OK] {filename:30s} — {patched}/{len(entries)} entries patched")

    print("\nDone. Run 'python -m evaluation.combine_benchmarks' to regenerate full_benchmark.json")


if __name__ == "__main__":
    main()
