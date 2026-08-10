"""Inter-agent communication bus utilities.

Provides helpers for the agent message bus and shared working memory.
Agents use these to emit messages for downstream consumption and to
read outputs from upstream agents.

Design
------
Since ``AgentState`` uses Pydantic ``BaseModel`` (not ``TypedDict``),
LangGraph applies "last write wins" for all fields.  The ``emit_message``
helper handles list accumulation manually by copying existing messages
and appending the new one.
"""

from __future__ import annotations

import logging
import time

from app.agents.state import AgentState, AgentMessage

logger = logging.getLogger(__name__)


def emit_message(
    state: AgentState,
    state_update: dict,
    sender: str,
    msg_type: str,
    content: str,
    metadata: dict | None = None,
) -> dict:
    """Append an agent message and mark the agent as completed.

    Merges the message into the provided ``state_update`` dict
    (mutated in-place) and returns it for convenience.

    Parameters
    ----------
    state : AgentState
        Current graph state — used to read existing messages.
    state_update : dict
        The dict that will be returned by the calling node.
    sender : str
        Agent name emitting the message (e.g. ``"deep_research"``).
    msg_type : str
        Message type tag (e.g. ``"research_findings"``).
    content : str
        The payload content (usually markdown or plain text).
    metadata : dict, optional
        Optional structured metadata (e.g. source count, sub-queries).

    Returns
    -------
    dict
        The same ``state_update`` dict, with ``agent_messages`` and
        ``completed_agents`` fields added/updated.
    """
    msg = AgentMessage(
        sender=sender,
        msg_type=msg_type,
        content=content,
        metadata=metadata or {},
        timestamp=time.time(),
    )

    # Accumulate: copy existing messages + append new one
    state_update["agent_messages"] = list(state.agent_messages) + [msg]

    # Track completion
    completed = list(state.completed_agents)
    if sender not in completed:
        completed.append(sender)
    state_update["completed_agents"] = completed

    logger.debug(
        "Agent '%s' emitted message type='%s' (%d chars).",
        sender,
        msg_type,
        len(content),
    )

    return state_update


def get_messages_from(
    state: AgentState,
    sender: str,
    msg_type: str | None = None,
) -> list[AgentMessage]:
    """Retrieve all messages from a specific agent.

    Parameters
    ----------
    state : AgentState
        Current graph state.
    sender : str
        Agent name to filter by.
    msg_type : str, optional
        If provided, further filter by message type.

    Returns
    -------
    list[AgentMessage]
        Matching messages in chronological order.
    """
    return [
        m
        for m in state.agent_messages
        if m.sender == sender and (msg_type is None or m.msg_type == msg_type)
    ]


def get_latest_message(
    state: AgentState,
    sender: str,
    msg_type: str | None = None,
) -> AgentMessage | None:
    """Get the most recent message from a specific agent."""
    messages = get_messages_from(state, sender, msg_type)
    return messages[-1] if messages else None


def get_upstream_context(state: AgentState) -> str:
    """Merge upstream agent outputs into a single context string.

    Used by downstream agents (e.g. drafting) to incorporate
    research findings and reasoning conclusions from earlier
    plan steps.

    Returns
    -------
    str
        Combined upstream context, or empty string if none.
    """
    parts: list[str] = []
    for msg in state.agent_messages:
        if msg.msg_type in ("research_findings", "reasoning_conclusion"):
            header = (
                f"## {msg.sender.replace('_', ' ').title()} — "
                f"{msg.msg_type.replace('_', ' ').title()}"
            )
            parts.append(f"{header}\n\n{msg.content}")

    return "\n\n---\n\n".join(parts)
