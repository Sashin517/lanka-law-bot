from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


DraftStatus = Literal["draft", "reviewed", "finalized", "archived"]
DraftActor = Literal["user", "agent"]
DraftOperationType = Literal[
    "insert",
    "replace",
    "delete",
    "format",
    "comment",
    "regenerate_section",
    "replace_section",
]
DraftExportFormat = Literal["docx", "pdf", "html", "markdown"]


class DraftDocumentSpec(BaseModel):
    document_type: str = Field(default="unknown", max_length=128)
    title: str = Field(min_length=1, max_length=512)
    instructions: str = Field(default="", max_length=8000)


class DraftEditScope(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    section_ids: list[str] = Field(default_factory=list)


class CreateDraftDocumentRequest(BaseModel):
    matter_id: str | None = Field(default=None, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    document_type: str = Field(default="unknown", max_length=128)
    editor_json: dict[str, Any] = Field(default_factory=dict)
    markdown_content: str = ""
    html_content: str = ""
    created_by: DraftActor = "agent"
    change_summary: str = "Initial draft created."


class UpdateDraftDocumentRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    document_type: str | None = Field(default=None, max_length=128)
    status: DraftStatus | None = None
    editor_json: dict[str, Any] | None = None
    markdown_content: str | None = None
    html_content: str | None = None
    change_summary: str = "User saved document edits."


class DraftDocumentResponse(BaseModel):
    document_id: str
    matter_id: str | None = None
    title: str
    document_type: str
    status: DraftStatus
    editor_json: dict[str, Any]
    markdown_content: str
    html_content: str
    created_by: DraftActor
    created_at: datetime
    updated_at: datetime
    current_version: int = 0


class DraftDocumentListItem(BaseModel):
    document_id: str
    matter_id: str | None = None
    title: str
    document_type: str
    status: DraftStatus
    created_by: DraftActor
    created_at: datetime
    updated_at: datetime
    current_version: int = 0


class DraftVersionResponse(BaseModel):
    version_id: str
    document_id: str
    version_number: int
    markdown_content: str
    change_summary: str
    changed_by: DraftActor
    agent_run_id: str | None = None
    context_snapshot_id: str | None = None
    created_at: datetime


class GenerateDocumentsRequest(BaseModel):
    matter_id: str | None = Field(default=None, max_length=128)
    prompt: str = Field(min_length=1, max_length=12000)
    document_specs: list[DraftDocumentSpec] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)


class GenerateDocumentsResponse(BaseModel):
    matter_id: str | None = None
    documents: list[DraftDocumentResponse]


class AgentEditDocumentRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=12000)
    scope: DraftEditScope = Field(default_factory=DraftEditScope)
    track_changes: bool = True


class DraftChangeResponse(BaseModel):
    change_id: str
    document_id: str
    version_id: str
    operation_type: DraftOperationType
    target: str
    before_text: str
    after_text: str
    rationale: str
    changed_by: DraftActor
    created_at: datetime


class AgentEditDocumentResponse(BaseModel):
    document: DraftDocumentResponse
    version: DraftVersionResponse
    changes: list[DraftChangeResponse]
    change_summary: str


class ExportDocumentResponse(BaseModel):
    document_id: str
    filename: str
    format: DraftExportFormat
    content_type: str
    content_base64: str
