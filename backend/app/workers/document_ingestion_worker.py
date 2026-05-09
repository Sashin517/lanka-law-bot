from __future__ import annotations

import json
import logging
from datetime import datetime

from app.database.session import SessionLocal, init_db
from app.models.document import DocumentChunk, IngestionJob, UserDocument
from app.services.document_parser import DocumentParser
from app.services.document_storage import DocumentStorage
from app.services.legal_chunker import ChunkingDocumentContext, LegalDocumentChunker
from app.services.user_document_vector_store import UserDocumentVectorStore
from app.services.voyage_embedding_service import VoyageEmbeddingService

logger = logging.getLogger(__name__)


def process_document_ingestion(job_id: str) -> None:
    init_db()
    db = SessionLocal()
    try:
        job = db.get(IngestionJob, job_id)
        if not job:
            logger.error("Ingestion job not found: %s", job_id)
            return
        document = db.get(UserDocument, job.document_id)
        if not document:
            _fail_job(db, job, None, "Document row missing.")
            return

        job.status = "processing"
        job.started_at = datetime.utcnow()
        job.attempt_count += 1
        document.status = "processing"
        document.error_message = None
        db.commit()

        storage = DocumentStorage()
        markdown_path = storage.markdown_path(
            document.tenant_id,
            document.matter_id,
            document.id,
        )
        parsed = DocumentParser().parse_to_markdown(
            document.stored_path,
            str(markdown_path),
            document.document_type if document.document_type != "unknown" else None,
        )
        document.markdown_path = parsed.markdown_path
        if document.document_type == "unknown":
            document.document_type = parsed.detected_type
        db.commit()

        chunk_context = ChunkingDocumentContext(
            tenant_id=document.tenant_id,
            user_id=document.user_id,
            matter_id=document.matter_id,
            document_id=document.id,
            filename=document.filename,
            file_hash=document.file_hash,
            document_type=document.document_type,
        )
        chunk_set = LegalDocumentChunker().chunk(parsed.markdown, chunk_context)
        chunks = chunk_set.vectorized_chunks
        if not chunks:
            raise RuntimeError("Document parsing produced no ingestible chunks.")

        vector_store = UserDocumentVectorStore()
        vector_store.ensure_collection()
        vector_store.delete_document(document.id, document.tenant_id)

        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        db.commit()

        embeddings = VoyageEmbeddingService().embed_documents([chunk.text for chunk in chunks])
        point_ids = vector_store.upsert_chunks(chunks, embeddings)

        for chunk, point_id in zip(chunks, point_ids):
            db.add(
                DocumentChunk(
                    id=chunk.id,
                    document_id=document.id,
                    parent_id=chunk.metadata.parent_id,
                    chunk_type=chunk.metadata.chunk_type,
                    chunk_strategy=chunk.metadata.chunk_strategy,
                    qdrant_point_id=point_id,
                    page_start=chunk.metadata.page_start,
                    page_end=chunk.metadata.page_end,
                    heading_path=json.dumps(chunk.metadata.heading_path),
                    clause_label=chunk.metadata.clause_label,
                    text_hash=chunk.metadata.text_hash,
                )
            )

        document.status = "completed"
        document.chunk_count = len(chunks)
        document.error_message = None
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.error_message = None
        db.commit()
        logger.info("Completed ingestion for document=%s chunks=%d", document.id, len(chunks))
    except Exception as exc:
        logger.exception("Document ingestion failed for job=%s", job_id)
        job = db.get(IngestionJob, job_id)
        document = db.get(UserDocument, job.document_id) if job else None
        _fail_job(db, job, document, str(exc))
    finally:
        db.close()


def _fail_job(
    db,
    job: IngestionJob | None,
    document: UserDocument | None,
    error_message: str,
) -> None:
    if job:
        job.status = "failed"
        job.completed_at = datetime.utcnow()
        job.error_message = error_message
    if document:
        document.status = "failed"
        document.error_message = error_message
    db.commit()
