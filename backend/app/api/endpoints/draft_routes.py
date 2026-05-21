from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db, init_db
from app.schemas.drafts import (
    AgentEditDocumentRequest,
    AgentEditDocumentResponse,
    CreateDraftDocumentRequest,
    DraftDocumentListItem,
    DraftDocumentResponse,
    DraftExportFormat,
    DraftVersionResponse,
    ExportDocumentResponse,
    GenerateDocumentsRequest,
    GenerateDocumentsResponse,
    UpdateDraftDocumentRequest,
)
from app.services.drafts import DraftNotFoundError, DraftWorkspaceService

router = APIRouter()
service = DraftWorkspaceService()


@router.post("", response_model=DraftDocumentResponse)
def create_draft_document(
    request: CreateDraftDocumentRequest,
    db: Session = Depends(get_db),
) -> DraftDocumentResponse:
    init_db()
    return service.create_document(db, request)


@router.post("/generate", response_model=GenerateDocumentsResponse)
async def generate_draft_documents(
    request: GenerateDocumentsRequest,
    db: Session = Depends(get_db),
) -> GenerateDocumentsResponse:
    init_db()
    return await service.generate_documents(db, request)


@router.get("", response_model=list[DraftDocumentListItem])
def list_draft_documents(
    matter_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[DraftDocumentListItem]:
    init_db()
    return service.list_documents(db, matter_id=matter_id)


@router.post("/batch-agent-edit", response_model=list[AgentEditDocumentResponse])
async def batch_agent_edit_draft_documents(
    request: AgentEditDocumentRequest,
    db: Session = Depends(get_db),
) -> list[AgentEditDocumentResponse]:
    init_db()
    document_ids = request.scope.document_ids
    if not document_ids:
        raise HTTPException(
            status_code=422,
            detail="scope.document_ids must include at least one draft document ID.",
        )
    try:
        return await service.batch_agent_edit(
            db=db,
            document_ids=document_ids,
            instruction=request.instruction,
            section_ids=request.scope.section_ids,
            track_changes=request.track_changes,
        )
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{draft_id}", response_model=DraftDocumentResponse)
def get_draft_document(
    draft_id: str,
    db: Session = Depends(get_db),
) -> DraftDocumentResponse:
    init_db()
    try:
        document = service.get_document(db, draft_id)
        return service.to_document_response(db, document)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{draft_id}", response_model=DraftDocumentResponse)
def update_draft_document(
    draft_id: str,
    request: UpdateDraftDocumentRequest,
    db: Session = Depends(get_db),
) -> DraftDocumentResponse:
    init_db()
    try:
        return service.update_document(db, draft_id, request)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{draft_id}/versions", response_model=list[DraftVersionResponse])
def list_draft_versions(
    draft_id: str,
    db: Session = Depends(get_db),
) -> list[DraftVersionResponse]:
    init_db()
    try:
        return service.list_versions(db, draft_id)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{draft_id}/agent-edit", response_model=AgentEditDocumentResponse)
async def agent_edit_draft_document(
    draft_id: str,
    request: AgentEditDocumentRequest,
    db: Session = Depends(get_db),
) -> AgentEditDocumentResponse:
    init_db()
    try:
        return await service.agent_edit_document(
            db=db,
            draft_id=draft_id,
            instruction=request.instruction,
            section_ids=request.scope.section_ids,
            track_changes=request.track_changes,
        )
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{draft_id}/export", response_model=ExportDocumentResponse)
def export_draft_document(
    draft_id: str,
    format: DraftExportFormat = Query(default="markdown"),
    db: Session = Depends(get_db),
) -> ExportDocumentResponse:
    init_db()
    try:
        return service.export_document(db, draft_id, format)
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
