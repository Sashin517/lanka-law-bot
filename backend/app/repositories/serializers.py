"""Stable repository DTO serialization for SQLAlchemy conversation models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.models.conversation import (
    AgentRun,
    Conversation,
    Message,
    MessageAttachment,
    MessageCitation,
)


def agent_run_to_record(agent_run: AgentRun) -> dict[str, Any]:
    return {
        "id": agent_run.id,
        "conversation_id": agent_run.conversation_id,
        "route": agent_run.route,
        "task_type": agent_run.task_type,
        "answer_mode": agent_run.answer_mode,
        "plan_type": agent_run.plan_type,
        "steps_executed": agent_run.steps_executed,
        "total_steps": agent_run.total_steps,
        "planning_reasoning": agent_run.planning_reasoning,
        "completed_agents": agent_run.completed_agents,
        "grounding_score": agent_run.grounding_score,
        "duration_ms": agent_run.duration_ms,
        "created_at": datetime_to_iso(agent_run.created_at),
    }


def _enum_value(value: str | Enum) -> str:
    return str(value.value) if isinstance(value, Enum) else str(value)


def datetime_to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def conversation_to_record(conversation: Conversation) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "title": conversation.title,
        "status": _enum_value(conversation.status),
        "query_mode": conversation.query_mode,
        "message_count": conversation.message_count,
        "last_message_preview": conversation.last_message_preview,
        "created_at": datetime_to_iso(conversation.created_at),
        "updated_at": datetime_to_iso(conversation.updated_at),
        "deleted_at": (
            datetime_to_iso(conversation.deleted_at)
            if conversation.deleted_at
            else None
        ),
    }


def citation_to_record(citation: MessageCitation) -> dict[str, Any]:
    return {
        "citation_id": citation.citation_id,
        "title": citation.title,
        "section": citation.section,
        "year": citation.year,
        "breadcrumb": citation.breadcrumb,
        "excerpt": citation.excerpt,
        "source_type": citation.source_type,
        "document_id": citation.document_id,
        "filename": citation.filename,
        "page_start": citation.page_start,
        "page_end": citation.page_end,
        "source_uri": citation.source_uri,
        "court": citation.court,
        "reporter_citation": citation.reporter_citation,
        "docket_number": citation.docket_number,
        "authoritative": citation.authoritative,
    }


def attachment_to_record(attachment: MessageAttachment) -> dict[str, Any]:
    return {
        "document_id": attachment.document_id,
        "filename": attachment.filename,
        "status": attachment.status,
    }


def message_to_record(message: Message) -> dict[str, Any]:
    citations = sorted(message.citations, key=lambda item: (item.citation_id, item.id))
    attachments = sorted(
        message.attachments, key=lambda item: (item.filename, item.document_id, item.id)
    )
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": _enum_value(message.role),
        "content": message.content,
        "markdown_content": message.markdown_content,
        "confidence": message.confidence,
        "disclaimer": message.disclaimer,
        "sequence_number": message.sequence_number,
        "token_count": message.token_count,
        "query_mode": message.query_mode,
        "agent_run_id": message.agent_run_id,
        "citations": [citation_to_record(item) for item in citations],
        "attachments": [attachment_to_record(item) for item in attachments],
        "created_at": datetime_to_iso(message.created_at),
    }
