"""Push a benchmark JSON to LangSmith as a versioned dataset.

Usage:
    cd backend
    python -m evaluation.upload_dataset --json benchmarks/datasets/full_benchmark.json --name "sllb-v1"
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from langsmith import Client


BACKEND_DIR = Path(__file__).resolve().parent.parent


def upload_benchmark(json_path: Path, dataset_name: str):
    client = Client()

    with open(json_path, encoding="utf-8") as f:
        benchmark = json.load(f)

    if not isinstance(benchmark, list):
        print("ERROR: benchmark JSON must be a top-level array.")
        sys.exit(1)

    # Create or retrieve existing dataset
    try:
        dataset = client.create_dataset(
            dataset_name,
            description=(
                f"LankaLawBot Sri Lankan Legal Benchmark — "
                f"{len(benchmark)} questions across "
                f"{len(set(e.get('category','') for e in benchmark))} categories"
            ),
        )
        print(f"Created new dataset: '{dataset_name}' (id={dataset.id})")
    except Exception as e:
        if "already exists" in str(e).lower() or "Conflict" in str(e):
            # Fetch existing
            datasets = list(client.list_datasets(dataset_name=dataset_name))
            if not datasets:
                raise
            dataset = datasets[0]
            print(f"Using existing dataset: '{dataset_name}' (id={dataset.id})")
        else:
            raise

    created = 0
    for item in benchmark:
        # Inputs — what the pipeline receives
        inputs = {
            "question": item["question"],
            "mode": item.get("mode", "quick_qa"),
            "document_ids": item.get("request", {}).get("document_ids", []),
            "matter_id": item.get("request", {}).get("matter_id"),
        }

        # Outputs — ground truth for evaluators
        outputs = {
            "expected_answer": item["ground_truth_answer"],
            "expected_route": item.get("expected_route", ""),
            "expected_task_type": item.get("expected_task_type", ""),
            "expected_answer_mode": item.get("expected_answer_mode", ""),
            "expected_target_corpus": item.get("expected_target_corpus", ""),
            "expected_needs_clarification": item.get("expected_needs_clarification", False),
            "expected_sources": item.get("expected_sources", []),
            "expected_confidence": item.get("expected_confidence", "medium"),
            "expected_grounding_min": item.get("expected_grounding_min", 0.7),
            "category": item.get("category", ""),
            "difficulty": item.get("difficulty", ""),
            "id": item.get("id", ""),
        }

        client.create_example(
            inputs=inputs,
            outputs=outputs,
            dataset_id=dataset.id,
        )
        created += 1

    print(f"\n✓ Uploaded {created} examples to dataset '{dataset_name}'")
    print(f"  View at: https://smith.langchain.com/")


def main():
    parser = argparse.ArgumentParser(description="Upload benchmark to LangSmith")
    parser.add_argument("--json", type=str, required=True, help="Path to benchmark JSON")
    parser.add_argument("--name", type=str, required=True, help="LangSmith dataset name")
    args = parser.parse_args()

    json_path = BACKEND_DIR / args.json
    if not json_path.exists():
        # Try as absolute path
        json_path = Path(args.json)
    if not json_path.exists():
        print(f"File not found: {args.json}")
        sys.exit(1)

    upload_benchmark(json_path, args.name)


if __name__ == "__main__":
    main()
