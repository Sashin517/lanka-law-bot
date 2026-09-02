"""Authenticated REST API for persistent research-chat conversations."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Annotated, Any, TypeVar
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runtime import get_graph
from app.agents.state import AgentState
from app.agents.streaming import (
    ExecutionStreamManager,
    FinalSuppressingEmitter,
    event_bus,
)
from app.api.sse import stream_channel, streaming_response
from app.auth.firebase_auth import get_current_user_id
from app.database.postgres_session import get_async_db
from app.repositories.exceptions import (
    ConversationNotFoundError,
    InvalidCursorError,
    InvalidRepositoryDataError,
)
from app.schemas.conversations import (
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationSummaryResponse,
    CreateConversationRequest,
    MessageListResponse,
    OperationStatusResponse,
    RenameConversationRequest,
    SendMessageRequest,
    SendMessageResponse,
)
from app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)
router = APIRouter()
T = TypeVar("T")

ConversationIdPath = Annotated[
    str,
    Path(min_length=1, max_length=64, description="Conversation identifier"),
]
DatabaseSession = Annotated[AsyncSession, Depends(get_async_db)]
CurrentUserId = Annotated[str, Depends(get_current_user_id)]


def get_conversation_service(
    session: DatabaseSession,
) -> ConversationService:
    """Assemble the service layer for one request-scoped database session."""
    return ConversationService(session)


def get_conversation_graph() -> Any:
    """Dependency seam for testing agent orchestration without external calls."""
    return get_graph()


def get_conversation_graph_loader() -> Callable[[], Any]:
    """Return a cheap loader so graph imports happen inside the SSE producer."""

    return get_graph


ConversationServiceDependency = Annotated[
    ConversationService,
    Depends(get_conversation_service),
]
ConversationGraphDependency = Annotated[Any, Depends(get_conversation_graph)]
ConversationGraphLoaderDependency = Annotated[
    Callable[[], Any],
    Depends(get_conversation_graph_loader),
]


@router.post(
    "",
    response_model=ConversationSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    body: CreateConversationRequest,
    user_id: CurrentUserId,
    service: ConversationServiceDependency,
) -> ConversationSummaryResponse:
    conversation = await _service_call(
        service.create_conversation(
            user_id=user_id,
            title=body.title,
            query_mode=body.query_mode.value,
        )
    )
    return ConversationSummaryResponse.model_validate(conversation)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    user_id: CurrentUserId,
    service: ConversationServiceDependency,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int = Query(default=30, ge=1, le=100),
) -> ConversationListResponse:
    conversations, next_cursor = await _service_call(
        service.list_conversations(user_id=user_id, cursor=cursor, limit=limit)
    )
    return ConversationListResponse(
        conversations=[
            ConversationSummaryResponse.model_validate(item) for item in conversations
        ],
        next_cursor=next_cursor,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: ConversationIdPath,
    user_id: CurrentUserId,
    service: ConversationServiceDependency,
) -> ConversationDetailResponse:
    conversation = await _service_call(
        service.get_conversation(conversation_id, user_id)
    )
    if conversation is None:
        raise _not_found()
    messages, next_cursor = await _service_call(
        service.get_messages(
            conversation_id,
            user_id=user_id,
            limit=50,
        )
    )
    return ConversationDetailResponse.model_validate(
        {
            **conversation,
            "messages": {"messages": messages, "next_cursor": next_cursor},
        }
    )


@router.patch(
    "/{conversation_id}/title",
    response_model=OperationStatusResponse,
)
async def rename_conversation(
    conversation_id: ConversationIdPath,
    body: RenameConversationRequest,
    user_id: CurrentUserId,
    service: ConversationServiceDependency,
) -> OperationStatusResponse:
    await _service_call(
        service.rename_conversation(conversation_id, user_id, body.title)
    )
    return OperationStatusResponse()


@router.delete(
    "/{conversation_id}",
    response_model=OperationStatusResponse,
)
async def delete_conversation(
    conversation_id: ConversationIdPath,
    user_id: CurrentUserId,
    service: ConversationServiceDependency,
) -> OperationStatusResponse:
    await _service_call(service.delete_conversation(conversation_id, user_id))
    return OperationStatusResponse()


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
)
async def list_messages(
    conversation_id: ConversationIdPath,
    user_id: CurrentUserId,
    service: ConversationServiceDependency,
    cursor: str | None = Query(default=None, max_length=2048),
    limit: int = Query(default=50, ge=1, le=200),
) -> MessageListResponse:
    messages, next_cursor = await _service_call(
        service.get_messages(
            conversation_id,
            user_id=user_id,
            cursor=cursor,
            limit=limit,
        )
    )
    return MessageListResponse.model_validate(
        {"messages": messages, "next_cursor": next_cursor}
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=SendMessageResponse,
)
async def send_message(
    conversation_id: ConversationIdPath,
    body: SendMessageRequest,
    user_id: CurrentUserId,
    service: ConversationServiceDependency,
    graph: ConversationGraphDependency,
) -> SendMessageResponse:
    """Persist a user turn, run the graph, then persist its response."""

    return await _execute_message(
        conversation_id=conversation_id,
        body=body,
        user_id=user_id,
        service=service,
        graph=graph,
    )


@router.post("/{conversation_id}/messages/stream")
async def send_message_stream(
    conversation_id: ConversationIdPath,
    body: SendMessageRequest,
    user_id: CurrentUserId,
    service: ConversationServiceDependency,
    graph_loader: ConversationGraphLoaderDependency,
) -> StreamingResponse:
    """Persist one conversation turn while streaming its graph activity."""

    session_id = str(uuid4())
    channel = event_bus.create_channel(session_id)
    stream_manager = ExecutionStreamManager(session_id, event_bus)
    graph_emitter = FinalSuppressingEmitter(stream_manager)
    graph_config: RunnableConfig = {"configurable": {"stream_emitter": graph_emitter}}

    logger.info(
        "Conversation SSE stream created: session=%s conversation=%s mode=%s",
        session_id,
        conversation_id,
        body.query_mode.value,
    )

    async def run_message() -> None:
        try:
            stream_manager.emit_stream_start(body.content, body.query_mode.value)
            # Import and build the graph in a worker only after the first SSE event
            # is queued.  Heartbeats remain available while cold initialization is
            # in progress, and the event loop is never blocked by model imports.
            graph = await asyncio.to_thread(graph_loader)
            response = await _execute_message(
                conversation_id=conversation_id,
                body=body,
                user_id=user_id,
                service=service,
                graph=graph,
                graph_config=graph_config,
            )
            stream_manager.emit_final(response.model_dump(mode="json"))
        except asyncio.CancelledError:
            logger.info(
                "Conversation SSE stream cancelled: session=%s conversation=%s",
                session_id,
                conversation_id,
            )
            raise
        except HTTPException as exc:
            logger.warning(
                "Conversation SSE request failed: session=%s status=%s",
                session_id,
                exc.status_code,
            )
            stream_manager.emit_error(_http_exception_message(exc))
        except Exception as exc:
            logger.exception(
                "Conversation SSE execution failed: session=%s conversation=%s",
                session_id,
                conversation_id,
            )
            stream_manager.emit_error(str(exc) or "Conversation request failed.")

    content = stream_channel(
        channel=channel,
        producer=run_message,
        close_channel=lambda: event_bus.close_channel(session_id),
    )
    return streaming_response(content)


async def _execute_message(
    *,
    conversation_id: str,
    body: SendMessageRequest,
    user_id: str,
    service: ConversationService,
    graph: Any,
    graph_config: RunnableConfig | None = None,
) -> SendMessageResponse:
    """Shared application service for JSON and SSE conversation adapters."""

    user_message = await _service_call(
        service.add_user_message(
            conversation_id=conversation_id,
            content=body.content,
            user_id=user_id,
            attachments=[item.model_dump() for item in body.attachments],
            query_mode=body.query_mode.value,
        )
    )
    context_messages = await _service_call(
        service.build_context_window(
            conversation_id,
            user_id=user_id,
            mode=body.query_mode.value,
            exclude_message_id=user_message["id"],
        )
    )

    initial_state = AgentState(
        question=body.content,
        mode=body.query_mode.value,
        document_ids=body.document_ids,
        working_memory={"conversation_context": context_messages},
    )
    graph_started = time.monotonic()
    try:
        if graph_config is None:
            final_state = await graph.ainvoke(initial_state.model_dump())
        else:
            final_state = await graph.ainvoke(
                initial_state.model_dump(),
                config=graph_config,
            )
        final_response = _extract_final_response(final_state)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Agent graph failed for conversation %s after saving user message %s.",
            conversation_id,
            user_message["id"],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI response generation failed; your message was saved.",
        ) from exc
    duration_ms = max(0, round((time.monotonic() - graph_started) * 1000))

    answer = _response_text(final_response, "answer")
    markdown_content = _optional_response_text(final_response, "markdown_content")
    if not answer:
        answer = markdown_content or ""
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI pipeline returned an empty response; your message was saved.",
        )

    assistant_message = await _service_call(
        service.add_assistant_message(
            conversation_id=conversation_id,
            content=answer,
            user_id=user_id,
            markdown_content=markdown_content,
            confidence=_optional_response_text(final_response, "confidence"),
            disclaimer=_optional_response_text(final_response, "disclaimer"),
            citations=_source_records(final_response.get("sources")),
            agent_run=_agent_run_metadata(final_response, duration_ms),
        )
    )
    encoded_response = jsonable_encoder(final_response)
    return SendMessageResponse.model_validate(
        {
            "user_message": user_message,
            "assistant_message": assistant_message,
            "response": encoded_response,
        }
    )


def _http_exception_message(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, str) and detail.strip():
        return detail
    return f"Conversation request failed with status {exc.status_code}."


async def _service_call(awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except ConversationNotFoundError as exc:
        raise _not_found() from exc
    except InvalidCursorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidRepositoryDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("Conversation database operation failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversation storage is temporarily unavailable.",
        ) from exc


def _extract_final_response(final_state: Any) -> dict[str, Any]:
    if isinstance(final_state, BaseModel):
        final_state = final_state.model_dump()
    if not isinstance(final_state, Mapping):
        raise TypeError("Agent graph returned an invalid state.")

    response = final_state.get("final_response")
    if isinstance(response, BaseModel):
        response = response.model_dump()
    if not isinstance(response, Mapping):
        raise TypeError("Agent graph did not produce a final response.")
    return dict(response)


def _source_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    records: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, BaseModel):
            records.append(item.model_dump())
        elif isinstance(item, Mapping):
            records.append(dict(item))
    return records


def _response_text(response: Mapping[str, Any], field: str) -> str:
    value = response.get(field)
    return value.strip() if isinstance(value, str) else ""


def _optional_response_text(response: Mapping[str, Any], field: str) -> str | None:
    value = _response_text(response, field)
    return value or None


def _agent_run_metadata(
    response: Mapping[str, Any], duration_ms: int
) -> dict[str, Any]:
    """Normalize public graph diagnostics into the persistence contract."""
    route_value = response.get("route")
    route = route_value if isinstance(route_value, Mapping) else {}
    trace_value = response.get("execution_trace")
    trace = trace_value if isinstance(trace_value, Mapping) else {}

    steps_value = trace.get("steps_executed")
    steps = _source_records(steps_value)
    completed_value = trace.get("completed_agents")
    completed_agents = (
        [item for item in completed_value if isinstance(item, str)]
        if isinstance(completed_value, list)
        else []
    )
    total_steps = trace.get("total_steps", len(steps))
    if isinstance(total_steps, bool) or not isinstance(total_steps, int):
        total_steps = len(steps)
    grounding_score = response.get("grounding_score", 0.0)
    if isinstance(grounding_score, bool) or not isinstance(
        grounding_score, (int, float)
    ):
        grounding_score = 0.0

    return {
        "route": _mapping_text(route, "route"),
        "task_type": _mapping_text(route, "task_type"),
        "answer_mode": _mapping_text(route, "answer_mode"),
        "plan_type": _mapping_text(trace, "plan_type"),
        "steps_executed": steps,
        "total_steps": max(0, total_steps),
        "planning_reasoning": _mapping_text(trace, "planning_reasoning") or "",
        "completed_agents": completed_agents,
        "grounding_score": min(1.0, max(0.0, float(grounding_score))),
        "duration_ms": duration_ms,
    }


def _mapping_text(mapping: Mapping[str, Any], field: str) -> str | None:
    value = mapping.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Conversation not found.",
    )
