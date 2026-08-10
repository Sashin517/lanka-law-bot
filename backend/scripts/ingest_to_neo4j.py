"""Local launcher for the canonical single-file Neo4j ingestion pipeline.

There is intentionally only one ingestion implementation. The root Colab file
owns parsing, identity, extraction, publication, and integrity behavior; this
script only maps local command-line paths to that implementation. Credentials
must be supplied through environment variables or Colab Secrets, never CLI
arguments (which are visible in process listings).
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PATH = REPOSITORY_ROOT / "act_and_case_law_ingestion_process_neo4j.py"


def _load_pipeline():
    spec = importlib.util.spec_from_file_location(
        "lankalaw_canonical_neo4j_ingestion", PIPELINE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load canonical pipeline at {PIPELINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the canonical LankaLaw Neo4j ingestion pipeline"
    )
    parser.add_argument("--acts-dir", required=True)
    parser.add_argument("--cases-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--work-dir", default="./lankalaw_neo4j_ingestion")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate the full corpus without API or Neo4j writes",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Republish documents even when the same source expression exists",
    )
    args = parser.parse_args()

    pipeline = _load_pipeline()
    pipeline.ACTS_DIR = str(Path(args.acts_dir).resolve())
    pipeline.CASES_DIR = str(Path(args.cases_dir).resolve())
    pipeline.METADATA_MANIFEST = str(Path(args.manifest).resolve())
    pipeline.WORK_DIR = str(Path(args.work_dir).resolve())
    pipeline.DRY_RUN = args.dry_run
    pipeline.RESUME_COMPLETED_DOCUMENTS = not args.no_resume
    pipeline.run()


if __name__ == "__main__":
    main()
