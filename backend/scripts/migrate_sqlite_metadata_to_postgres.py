"""One-time transactional migration of legacy metadata into PostgreSQL.

Run this only after ``alembic upgrade head``. Existing PostgreSQL rows are
never overwritten: matching rows are accepted, conflicting rows abort the
whole transaction, and missing rows are inserted in foreign-key-safe order.
"""

from __future__ import annotations

import argparse
import importlib
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Table, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database.postgres_session import Base, sync_engine

for model_module in ("app.models.document", "app.models.draft"):
    importlib.import_module(model_module)

TABLE_ORDER: tuple[str, ...] = (
    "user_documents",
    "ingestion_jobs",
    "document_chunks",
    "draft_documents",
    "draft_context_snapshots",
    "draft_document_versions",
    "draft_document_changes",
)

LEGACY_COLUMN_ALIASES: dict[str, dict[str, str]] = {
    "document_chunks": {"vector_record_id": "qdrant_point_id"},
}

LEGACY_DEFAULTS: dict[str, dict[str, Any]] = {
    "document_chunks": {
        "page_start": None,
        "page_end": None,
        "heading_path": None,
        "clause_label": None,
    },
    "draft_document_versions": {
        "source_refs": "[]",
        "parent_version_id": None,
        "agent_run_id": None,
        "context_snapshot_id": None,
    },
}


class MigrationConflictError(RuntimeError):
    """Raised when a destination row would be silently overwritten."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to the legacy metadata.sqlite3 file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report the migration, then roll back PostgreSQL.",
    )
    parser.add_argument(
        "--delete-source-after-verify",
        action="store_true",
        help="Delete the source file only after a committed, verified migration.",
    )
    return parser.parse_args()


def migrate(
    source_path: Path,
    *,
    dry_run: bool = False,
    delete_source_after_verify: bool = False,
) -> dict[str, int]:
    source_path = source_path.resolve(strict=True)
    if not source_path.is_file():
        raise ValueError(f"SQLite source is not a file: {source_path}")
    if delete_source_after_verify and dry_run:
        raise ValueError("Cannot delete the source during a dry run.")

    source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        _validate_source_tables(source)
        source_rows = {
            table_name: _read_source_rows(source, table_name)
            for table_name in TABLE_ORDER
        }
    finally:
        source.close()

    migrated_counts: dict[str, int] = {}
    with sync_engine.connect() as destination:
        transaction = destination.begin()
        try:
            for table_name in TABLE_ORDER:
                table = Base.metadata.tables[table_name]
                rows = [
                    _coerce_row(table, row, table_name)
                    for row in source_rows[table_name]
                ]
                migrated_counts[table_name] = _migrate_table(
                    destination,
                    table,
                    rows,
                )

            _verify_ids(destination, source_rows)
            if dry_run:
                transaction.rollback()
            else:
                transaction.commit()
        except Exception:
            if transaction.is_active:
                transaction.rollback()
            raise

    action = "validated" if dry_run else "migrated"
    for table_name in TABLE_ORDER:
        source_count = len(source_rows[table_name])
        inserted_count = migrated_counts[table_name]
        print(
            f"{table_name}: source={source_count}, "
            f"inserted={inserted_count}, {action}=true"
        )

    if delete_source_after_verify:
        source_path.unlink()
        print(f"Deleted verified legacy source: {source_path}")

    return migrated_counts


def _validate_source_tables(source: sqlite3.Connection) -> None:
    available = {
        str(row[1])
        for row in source.execute("PRAGMA table_list")
        if str(row[2]).casefold() == "table"
    }
    missing = set(TABLE_ORDER) - available
    if missing:
        raise ValueError(
            "Legacy source is missing required tables: " + ", ".join(sorted(missing))
        )


def _read_source_rows(
    source: sqlite3.Connection,
    table_name: str,
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in source.execute(f'SELECT * FROM "{table_name}"')]
    if table_name == "draft_document_versions":
        rows.sort(key=lambda row: (int(row.get("version_number") or 0), row["id"]))
    return rows


def _coerce_row(
    table: Table,
    source_row: Mapping[str, Any],
    table_name: str,
) -> dict[str, Any]:
    aliases = LEGACY_COLUMN_ALIASES.get(table_name, {})
    defaults = LEGACY_DEFAULTS.get(table_name, {})
    result: dict[str, Any] = {}

    for column in table.columns:
        source_name = column.name
        if source_name not in source_row:
            source_name = aliases.get(column.name, column.name)

        if source_name in source_row:
            value = source_row[source_name]
        elif column.name in defaults:
            value = defaults[column.name]
        elif column.nullable:
            value = None
        else:
            raise ValueError(
                f"{table_name}.{column.name} is required but absent from legacy data."
            )

        if value is not None and isinstance(column.type, DateTime):
            value = _parse_datetime(value)
        result[column.name] = value

    return result


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise TypeError(f"Unsupported timestamp value: {value!r}")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _migrate_table(
    destination: Any,
    table: Table,
    rows: Sequence[dict[str, Any]],
) -> int:
    if not rows:
        return 0

    source_by_id = {str(row["id"]): row for row in rows}
    existing_rows = destination.execute(
        select(table).where(table.c.id.in_(source_by_id))
    ).mappings()
    existing_by_id = {str(row["id"]): dict(row) for row in existing_rows}

    for row_id, existing in existing_by_id.items():
        incoming = source_by_id[row_id]
        conflicts = [
            column.name
            for column in table.columns
            if _normalise(existing[column.name]) != _normalise(incoming[column.name])
        ]
        if conflicts:
            raise MigrationConflictError(
                f"Conflicting PostgreSQL row {table.name}.{row_id}; "
                f"columns differ: {', '.join(conflicts)}"
            )

    missing_rows = [
        row for row_id, row in source_by_id.items() if row_id not in existing_by_id
    ]
    if missing_rows:
        destination.execute(postgres_insert(table), missing_rows)
    return len(missing_rows)


def _verify_ids(destination: Any, source_rows: Mapping[str, Sequence[dict]]) -> None:
    for table_name in TABLE_ORDER:
        table = Base.metadata.tables[table_name]
        expected_ids = {str(row["id"]) for row in source_rows[table_name]}
        if not expected_ids:
            continue
        stored_ids = {
            str(value)
            for value in destination.scalars(
                select(table.c.id).where(table.c.id.in_(expected_ids))
            )
        }
        missing = expected_ids - stored_ids
        if missing:
            raise RuntimeError(
                f"PostgreSQL verification failed for {table_name}; "
                f"missing {len(missing)} IDs."
            )


def _normalise(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat(timespec="microseconds")
    return value


def main() -> None:
    args = parse_args()
    migrate(
        args.source,
        dry_run=args.dry_run,
        delete_source_after_verify=args.delete_source_after_verify,
    )


if __name__ == "__main__":
    main()
