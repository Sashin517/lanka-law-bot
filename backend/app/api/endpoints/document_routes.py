from __future__ import annotations

from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.database.session import get_db, init_db
from app.models.document import DocumentChunk, IngestionJob, UserDocument
from app.schemas.documents import (
    DeleteDocumentResponse,
    DocumentListItem,
    DocumentStatusResponse,
    UploadDocumentResponse,
)
from app.services.ingestion.document_storage import DocumentStorage
from app.services.ingestion.ingestion_jobs import IngestionJobService
from app.services.retrieval.user_document_vector_store import UserDocumentVectorStore
from app.workers.document_ingestion_worker import process_document_ingestion

router = APIRouter()

LOCAL_TENANT_ID = "local"
LOCAL_USER_ID = "local_user"


@router.post("/upload", response_model=UploadDocumentResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    matter_id: str | None = Form(default=None),
    document_type: str = Form(default="unknown"),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> UploadDocumentResponse:
    init_db()
    document_id = str(uuid4())
    storage = DocumentStorage()
    stored = await storage.save_upload(
        file=file,
        tenant_id=LOCAL_TENANT_ID,
        matter_id=matter_id,
        document_id=document_id,
    )

    document = UserDocument(
        id=document_id,
        tenant_id=LOCAL_TENANT_ID,
        user_id=LOCAL_USER_ID,
        matter_id=matter_id,
        filename=stored.original_filename,
        title=title,
        stored_path=stored.stored_path,
        mime_type=stored.mime_type,
        file_hash=stored.file_hash,
        document_type=document_type or "unknown",
        status="queued",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    job = IngestionJobService().create_job(db, document)
    background_tasks.add_task(process_document_ingestion, job.id)

    return UploadDocumentResponse(
        document_id=document.id,
        job_id=job.id,
        filename=document.filename,
        status="queued",
    )


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(
    document_id: str,
    db: Session = Depends(get_db),
) -> DocumentStatusResponse:
    init_db()
    document = _get_document_or_404(db, document_id)
    job = (
        db.query(IngestionJob)
        .filter(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.started_at.desc().nullslast(), IngestionJob.id.desc())
        .first()
    )
    return _status_response(document, job)


@router.get("", response_model=list[DocumentListItem])
def list_documents(
    matter_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[DocumentListItem]:
    init_db()
    query = db.query(UserDocument).filter(
        UserDocument.tenant_id == LOCAL_TENANT_ID,
        UserDocument.user_id == LOCAL_USER_ID,
    )
    if matter_id:
        query = query.filter(UserDocument.matter_id == matter_id)
    documents = query.order_by(UserDocument.created_at.desc()).all()
    return [
        DocumentListItem(
            document_id=document.id,
            filename=document.filename,
            title=document.title,
            matter_id=document.matter_id,
            document_type=document.document_type,
            status=document.status,
            chunk_count=document.chunk_count,
            created_at=document.created_at,
        )
        for document in documents
    ]


@router.delete("/{document_id}", response_model=DeleteDocumentResponse)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> DeleteDocumentResponse:
    init_db()
    document = _get_document_or_404(db, document_id)

    try:
        UserDocumentVectorStore().delete_document(document.id, document.tenant_id)
    except Exception as exc:
        if document.status == "completed":
            raise HTTPException(
                status_code=502, detail=f"Failed to delete Pinecone records: {exc}"
            ) from exc

    DocumentStorage().delete_document_files(
        document.stored_path, document.markdown_path
    )
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
    db.delete(document)
    db.commit()
    return DeleteDocumentResponse(document_id=document_id)


def _get_document_or_404(db: Session, document_id: str) -> UserDocument:
    document = (
        db.query(UserDocument)
        .filter(
            UserDocument.id == document_id,
            UserDocument.tenant_id == LOCAL_TENANT_ID,
            UserDocument.user_id == LOCAL_USER_ID,
        )
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


def _status_response(
    document: UserDocument,
    job: IngestionJob | None,
) -> DocumentStatusResponse:
    return DocumentStatusResponse(
        document_id=document.id,
        job_id=job.id if job else None,
        filename=document.filename,
        status=document.status,
        chunk_count=document.chunk_count,
        error=document.error_message or (job.error_message if job else None),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )
