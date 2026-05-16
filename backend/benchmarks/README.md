# Sri Lankan Legal Benchmark (SLLB) — Dataset Documentation

## Overview

This benchmark evaluates the LankaLawBot RAG pipeline across **7 question categories** that map to the system's LangGraph worker nodes.

## Categories

| Category | Target Count | Route | Needs Fixture? |
|---|---|---|---|
| `quick_qa` | 12 | `quick_qa` | No |
| `deep_research` | 8 | `deep_research` | No |
| `reasoning` | 8 | `reasoning` | No |
| `drafting` | 5 | `drafting` | No |
| `review` | 6 | `review` | Yes |
| `verify` | 6 | `quick_qa` | No |
| `clarification` | 5 | `review` | No |
| **Total** | **50** | | |

## JSON Schema

Every entry follows the unified schema defined in the implementation plan. See `datasets/quick_qa.json` for a complete example.

## Ground Truth Curation Process

1. **Drafting**: Questions crafted from Acts in the corpus
2. **Answer Verification**: Cross-checked against actual statutory text
3. **Expert Review**: Validated by legal domain experts
4. **Version Control**: Stored as versioned JSON files

## Fixture Documents

Located in `fixtures/`. These are intentionally-flawed legal documents used by `review`-category tests. Each contains specific legal defects that the system should identify.

## Usage

```bash
# Combine all category files into full_benchmark.json
python -m evaluation.combine_benchmarks

# Upload review fixtures to Qdrant (patches document_ids)
python -m evaluation.upload_fixtures --benchmark benchmarks/datasets/review.json

# Re-combine after patching
python -m evaluation.combine_benchmarks

# Upload to LangSmith
python -m evaluation.upload_dataset --json benchmarks/datasets/full_benchmark.json --name "sllb-v1"
```

# Combine into full benchmark
python -m evaluation.combine_benchmarks

# Upload fixtures (attached documents) to Qdrant
python -m evaluation.upload_fixtures --benchmark benchmarks/datasets/review.json

# Re-combine and upload to LangSmith
python -m evaluation.combine_benchmarks
python -m evaluation.upload_dataset --json benchmarks/datasets/full_benchmark.json --name "sllb-v2"

# Main LangSmith Pipeline Evaluation
python -m evaluation.run_evaluation --dataset "sllb-v2" --prefix "v2-deterministic-routing"

# Collect & Cache (Runs the pipeline, no RAGAS metrics yet)
python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json --collect-only

# Batch Evaluation (Runs RAGAS metrics on 10 samples per day)
# Day 1
python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json --cached --limit 10 --offset 0

# Day 2
python -m evaluation.ragas_eval --benchmark benchmarks/datasets/full_benchmark.json --cached --limit 10 --offset 10

# Ablation Study
# Run all ablation configs (one per day recommended due to quota)
python -m evaluation.ablation_runner --benchmark benchmarks/datasets/full_benchmark.json

# Or run a specific config
python -m evaluation.ablation_runner --benchmark benchmarks/datasets/full_benchmark.json --configs dense_only
