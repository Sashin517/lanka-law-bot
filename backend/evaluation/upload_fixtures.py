"""Upload review fixture documents into Qdrant and patch benchmark JSONs with real document IDs.

Only processes entries where requires_user_document == true and document_fixture is present.

Usage:
    cd backend
    python -m evaluation.upload_fixtures --benchmark benchmarks/datasets/review.json
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from app.database.session import SessionLocal, init_db
from app.models.document import IngestionJob, UserDocument
from app.services.ingestion.document_storage import DocumentStorage
from app.services.ingestion.ingestion_jobs import IngestionJobService
from app.workers.document_ingestion_worker import process_document_ingestion

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
TENANT_ID = "local"
USER_ID = "local_user"


def ingest_fixture(fixture: dict, backend_dir: Path) -> str:
    """Ingest a single fixture document and return its document_id."""
    fixture_path = backend_dir / fixture["fixture_path"]
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")

    document_id = str(uuid4())
    matter_id = fixture.get("matter_id")
    doc_type = fixture.get("document_type", "unknown")
    title = fixture.get("title", fixture_path.stem)

    init_db()
    db = SessionLocal()
    try:
        # Store the markdown file directly (fixtures are .md)
        storage = DocumentStorage()
        matter_part = storage.safe_path_part(matter_id or "general")
        target_dir = (
            Path(storage.upload_root)
            / storage.safe_path_part(TENANT_ID)
            / matter_part
            / document_id
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "original.md"

        # Copy fixture content
        content = fixture_path.read_bytes()
        target_path.write_bytes(content)

        import hashlib

        file_hash = hashlib.sha256(content).hexdigest()

        # Create DB record
        document = UserDocument(
            id=document_id,
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            matter_id=matter_id,
            filename=fixture_path.name,
            title=title,
            stored_path=str(target_path),
            mime_type="text/markdown",
            file_hash=file_hash,
            document_type=doc_type,
            status="queued",
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        # Create ingestion job
        job = IngestionJobService().create_job(db, document)
        db.commit()

        # Run ingestion synchronously
        logger.info("Ingesting fixture: %s (id=%s)", title, document_id)
        process_document_ingestion(job.id)

        # Verify status
        db.refresh(document)
        if document.status != "completed":
            raise RuntimeError(
                f"Ingestion failed for {title}: status={document.status}, "
                f"error={document.error_message}"
            )

        logger.info(
            "  ✓ Ingested: %s — %d chunks",
            title,
            document.chunk_count or 0,
        )
        return document_id

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Upload fixture documents for review benchmarks"
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        required=True,
        help="Path to benchmark JSON (relative to backend/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List fixtures without uploading",
    )
    args = parser.parse_args()

    benchmark_path = BACKEND_DIR / args.benchmark
    if not benchmark_path.exists():
        print(f"Benchmark file not found: {benchmark_path}")
        sys.exit(1)

    with open(benchmark_path, encoding="utf-8") as f:
        entries = json.load(f)

    fixture_entries = [
        (i, e)
        for i, e in enumerate(entries)
        if e.get("requires_user_document") and e.get("document_fixture")
    ]

    if not fixture_entries:
        print("No fixture entries found in this benchmark.")
        return

    print(f"Found {len(fixture_entries)} fixture entries in {benchmark_path.name}\n")

    mapping: dict[str, str] = {}  # fixture_path -> document_id
    patched = False

    for idx, entry in fixture_entries:
        fixture = entry["document_fixture"]
        fixture_path = fixture["fixture_path"]

        if args.dry_run:
            print(f"  [DRY] {entry['id']} → {fixture_path}")
            continue

        # Skip if already uploaded (check mapping)
        if fixture_path in mapping:
            doc_id = mapping[fixture_path]
            logger.info("  Reusing %s → %s", fixture_path, doc_id)
        else:
            doc_id = ingest_fixture(fixture, BACKEND_DIR)
            mapping[fixture_path] = doc_id

        # Patch the entry
        entries[idx]["request"]["document_ids"] = [doc_id]
        patched = True

    if patched:
        # Write patched benchmark
        with open(benchmark_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        print(f"\n✓ Patched {len(fixture_entries)} entries in {benchmark_path.name}")

        # Save mapping for reference
        mapping_path = benchmark_path.parent / ".fixture_mapping.json"
        with open(mapping_path, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
        print(f"✓ Mapping saved to {mapping_path.name}")

    if args.dry_run:
        print("\n(Dry run — no changes made)")


if __name__ == "__main__":
    main()
