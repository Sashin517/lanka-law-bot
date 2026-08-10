"""Opt-in full-corpus preflight for the canonical Colab ingestion pipeline.

Run with:
  RUN_NEO4J_FULL_CORPUS_TEST=1 \
  LEGAL_CORPUS_MANIFEST=/absolute/path/legal_corpus_manifest.json \
  pytest backend/tests/test_neo4j_full_corpus_integration.py -q

This performs Docling/OCR parsing and every publication metadata/conflict gate,
but DRY_RUN guarantees that no API or Neo4j write is attempted.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import act_and_case_law_ingestion_process_neo4j as ingestion


@pytest.mark.skipif(
    os.environ.get("RUN_NEO4J_FULL_CORPUS_TEST") != "1",
    reason="set RUN_NEO4J_FULL_CORPUS_TEST=1 to run OCR/full-corpus preflight",
)
def test_full_corpus_passes_production_preflight(tmp_path):
    manifest = Path(os.environ["LEGAL_CORPUS_MANIFEST"]).resolve()
    assert manifest.is_file(), f"manifest not found: {manifest}"
    ingestion.ACTS_DIR = str(REPOSITORY_ROOT / "Contract Law Acts")
    ingestion.CASES_DIR = str(REPOSITORY_ROOT / "Contract Case Laws")
    ingestion.METADATA_MANIFEST = str(manifest)
    ingestion.WORK_DIR = str(tmp_path / "neo4j-full-corpus-preflight")
    ingestion.DRY_RUN = True
    ingestion.FORCE_REPARSE = False
    ingestion.run()
