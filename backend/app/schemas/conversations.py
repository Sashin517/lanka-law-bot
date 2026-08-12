"""Validated request and response contracts for conversation APIs."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.requests import QueryMode

ConversationId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]
DocumentId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]


class StrictRequestModel(BaseModel):
    """Reject unknown client fields instead of silently discarding mistakes."""

    model_config = ConfigDict(extra="forbid")


class CreateConversationRequest(StrictRequestModel):
    title: str = Field(default="New Chat", min_length=1, max_length=512)
    query_mode: QueryMode = QueryMode.QUICK_QA

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized


class RenameConversationRequest(StrictRequestModel):
    title: str = Field(min_length=1, max_length=512)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized


class MessageAttachmentRequest(StrictRequestModel):
    document_id: DocumentId
    filename: str = Field(min_length=1, max_length=512)
    status: str = Field(default="completed", min_length=1, max_length=32)

    @field_validator("filename", "status")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class SendMessageRequest(StrictRequestModel):
    content: str = Field(min_length=1, max_length=100_000)
    query_mode: QueryMode = QueryMode.QUICK_QA
    document_ids: list[DocumentId] = Field(default_factory=list, max_length=100)
    attachments: list[MessageAttachmentRequest] = Field(
        default_factory=list, max_length=100
    )

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value.strip()

    @field_validator("document_ids")
    @classmethod
    def reject_duplicate_document_ids(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("document_ids must not contain duplicates")
        return values


class ConversationSummaryResponse(BaseModel):
    id: str
    title: str
    query_mode: QueryMode
    message_count: int = Field(ge=0)
    last_message_preview: str
    created_at: str
    updated_at: str


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummaryResponse]
    next_cursor: str | None = None


class CitationResponse(BaseModel):
    citation_id: str
    title: str
    section: str | None = None
    year: int = Field(default=0, ge=0)
    breadcrumb: str | None = None
    excerpt: str = ""
    source_type: str | None = None
    document_id: str | None = None
    filename: str | None = None
    page_start: int | None = Field(default=None, ge=0)
    page_end: int | None = Field(default=None, ge=0)
    source_uri: str | None = None
    court: str | None = None
    reporter_citation: str | None = None
    docket_number: str | None = None
    authoritative: bool | None = None


class AttachmentResponse(BaseModel):
    document_id: str
    filename: str
    status: str


class MessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    markdown_content: str | None = None
    confidence: str | None = None
    disclaimer: str | None = None
    sequence_number: int = Field(ge=0)
    query_mode: QueryMode | None = None
    citations: list[CitationResponse] = Field(default_factory=list)
    attachments: list[AttachmentResponse] = Field(default_factory=list)
    created_at: str


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    next_cursor: str | None = None


class ConversationDetailResponse(ConversationSummaryResponse):
    status: Literal["active", "archived"]
    messages: MessageListResponse


class OperationStatusResponse(BaseModel):
    status: Literal["ok"] = "ok"


class SendMessageResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
    response: dict[str, Any]
