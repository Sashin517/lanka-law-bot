from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.document import IngestionJob, UserDocument


class IngestionJobService:
    def create_job(self, db: Session, document: UserDocument) -> IngestionJob:
        job = IngestionJob(
            id=str(uuid4()),
            document_id=document.id,
            status="queued",
            attempt_count=0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def latest_job_for_document(self, db: Session, document_id: str) -> IngestionJob | None:
        return (
            db.query(IngestionJob)
            .filter(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.started_at.desc().nullslast(), IngestionJob.id.desc())
            .first()
        )
