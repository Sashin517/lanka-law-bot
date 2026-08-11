"""Persistence service for immutable draft-version snapshots."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.draft import DraftDocument, DraftDocumentVersion
from app.schemas.responses import DraftVersionSnapshot


class DraftVersionNotFoundError(LookupError):
    """Raised when the requested draft does not exist."""


class DraftVersionConflictError(ValueError):
    """Raised when a snapshot would violate the immutable version chain."""


class DraftVersionService:
    """Store and retrieve append-only version mementos."""

    def save(
        self,
        db: Session,
        snapshot: DraftVersionSnapshot,
    ) -> DraftVersionSnapshot:
        self._require_draft(db, snapshot.draft_id)
        existing = db.get(DraftDocumentVersion, snapshot.id)
        if existing:
            persisted = self._to_snapshot(existing)
            if _snapshots_are_equivalent(persisted, snapshot):
                return persisted
            raise DraftVersionConflictError(
                f"Version ID '{snapshot.id}' already identifies another snapshot."
            )

        latest = (
            db.query(DraftDocumentVersion)
            .filter(DraftDocumentVersion.document_id == snapshot.draft_id)
            .order_by(DraftDocumentVersion.version_number.desc())
            .first()
        )
        expected_number = (latest.version_number if latest else 0) + 1
        if snapshot.version_number != expected_number:
            raise DraftVersionConflictError(
                f"Expected version_number {expected_number}, got {snapshot.version_number}."
            )

        expected_parent = latest.id if latest else None
        if snapshot.parent_version_id != expected_parent:
            raise DraftVersionConflictError(
                "parent_version_id must reference the latest persisted version."
            )

        version = DraftDocumentVersion(
            id=snapshot.id,
            document_id=snapshot.draft_id,
            version_number=snapshot.version_number,
            editor_json=json.dumps(snapshot.content_json, separators=(",", ":")),
            markdown_content=snapshot.content_markdown,
            source_refs=json.dumps(snapshot.sources, separators=(",", ":")),
            change_summary=snapshot.edit_summary,
            changed_by="agent" if snapshot.created_by == "ai" else "user",
            parent_version_id=snapshot.parent_version_id,
            created_at=_parse_created_at(snapshot.created_at),
        )
        db.add(version)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise DraftVersionConflictError(
                "The version chain changed while this snapshot was being saved."
            ) from exc
        db.refresh(version)
        return self._to_snapshot(version)

    def list_for_draft(
        self,
        db: Session,
        draft_id: str,
    ) -> list[DraftVersionSnapshot]:
        self._require_draft(db, draft_id)
        versions = (
            db.query(DraftDocumentVersion)
            .filter(DraftDocumentVersion.document_id == draft_id)
            .order_by(DraftDocumentVersion.version_number.asc())
            .all()
        )
        return [self._to_snapshot(version) for version in versions]

    @staticmethod
    def _require_draft(db: Session, draft_id: str) -> None:
        if db.get(DraftDocument, draft_id) is None:
            raise DraftVersionNotFoundError(
                f"Draft document '{draft_id}' was not found."
            )

    @staticmethod
    def _to_snapshot(version: DraftDocumentVersion) -> DraftVersionSnapshot:
        return DraftVersionSnapshot(
            id=version.id,
            draft_id=version.document_id,
            version_number=version.version_number,
            content_json=_decode_json_object(version.editor_json),
            content_markdown=version.markdown_content,
            sources=_decode_json_list(version.source_refs),
            created_at=_as_utc(version.created_at).isoformat(),
            created_by="ai" if version.changed_by == "agent" else "user",
            edit_summary=version.change_summary,
            parent_version_id=version.parent_version_id,
        )


def _parse_created_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DraftVersionConflictError(
            "created_at must be an ISO-8601 timestamp."
        ) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _snapshots_are_equivalent(
    persisted: DraftVersionSnapshot,
    requested: DraftVersionSnapshot,
) -> bool:
    persisted_data = persisted.model_dump(exclude={"created_at"})
    requested_data = requested.model_dump(exclude={"created_at"})
    return (
        persisted_data == requested_data
        and _parse_created_at(persisted.created_at)
        == _parse_created_at(requested.created_at)
    )


def _decode_json_object(value: str) -> dict:
    try:
        decoded = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _decode_json_list(value: str) -> list[dict]:
    try:
        decoded = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(decoded, list):
        return []
    return [item for item in decoded if isinstance(item, dict)]
