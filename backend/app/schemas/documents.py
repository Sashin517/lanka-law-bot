from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


DocumentStatus = Literal["queued", "processing", "completed", "failed"]


class UploadDocumentResponse(BaseModel):
    document_id: str
    job_id: str
    filename: str
    status: Literal["queued"]


class DocumentStatusResponse(BaseModel):
    document_id: str
    job_id: str | None
    filename: str
    status: DocumentStatus
    chunk_count: int = 0
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentListItem(BaseModel):
    document_id: str
    filename: str
    title: str | None = None
    matter_id: str | None = None
    document_type: str
    status: DocumentStatus
    chunk_count: int
    created_at: datetime | None = None


class DeleteDocumentResponse(BaseModel):
    document_id: str
    deleted: bool = True


class UserDocumentMetadata(BaseModel):
    source_type: Literal["user_document"] = "user_document"
    tenant_id: str
    user_id: str
    matter_id: str | None
    document_id: str
    filename: str
    file_hash: str
    document_type: str
    page_start: int | None = None
    page_end: int | None = None
    heading_path: list[str] = Field(default_factory=list)
    clause_label: str | None = None
    chunk_id: str
    parent_id: str | None = None
    chunk_type: Literal["parent", "child", "section_summary"]
    chunk_strategy: str
    text_hash: str
    embedding_model: str = "llama-text-embed-v2"
    embedding_dimension: int = 2048
    created_at: str
