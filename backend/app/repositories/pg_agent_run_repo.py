"""PostgreSQL repository for auditable agent execution records."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import AgentRun
from app.repositories.exceptions import InvalidRepositoryDataError
from app.repositories.interfaces import AgentRunRepositoryInterface, RepositoryRecord
from app.repositories.serializers import agent_run_to_record


class PgAgentRunRepository(AgentRunRepositoryInterface):
    """Persist normalized graph diagnostics in the active transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        conversation_id: str,
        *,
        route: str | None = None,
        task_type: str | None = None,
        answer_mode: str | None = None,
        plan_type: str | None = None,
        steps_executed: Sequence[Mapping[str, Any]] | None = None,
        total_steps: int = 0,
        planning_reasoning: str = "",
        completed_agents: Sequence[str] | None = None,
        grounding_score: float = 0.0,
        duration_ms: int = 0,
    ) -> RepositoryRecord:
        total_steps = _nonnegative_int(total_steps, "total_steps")
        duration_ms = _nonnegative_int(duration_ms, "duration_ms")
        grounding_score = _score(grounding_score)
        normalized_steps = _steps(steps_executed or ())
        normalized_agents = _agents(completed_agents or ())
        if not isinstance(planning_reasoning, str):
            raise InvalidRepositoryDataError("planning_reasoning must be a string.")

        run = AgentRun(
            id=str(uuid4()),
            conversation_id=conversation_id,
            route=_optional_text(route, "route", 64),
            task_type=_optional_text(task_type, "task_type", 64),
            answer_mode=_optional_text(answer_mode, "answer_mode", 64),
            plan_type=_optional_text(plan_type, "plan_type", 32),
            steps_executed=json.dumps(normalized_steps, ensure_ascii=False),
            total_steps=total_steps,
            planning_reasoning=planning_reasoning.strip(),
            completed_agents=json.dumps(normalized_agents, ensure_ascii=False),
            grounding_score=grounding_score,
            duration_ms=duration_ms,
        )
        self._session.add(run)
        await self._session.flush()
        return agent_run_to_record(run)


def _optional_text(value: str | None, field: str, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidRepositoryDataError(f"{field} must be a string.")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise InvalidRepositoryDataError(
            f"{field} cannot exceed {max_length} characters."
        )
    return normalized or None


def _nonnegative_int(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidRepositoryDataError(f"{field} must be an integer.")
    if value < 0:
        raise InvalidRepositoryDataError(f"{field} cannot be negative.")
    return value


def _score(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidRepositoryDataError("grounding_score must be numeric.")
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        raise InvalidRepositoryDataError("grounding_score must be between 0 and 1.")
    return normalized


def _steps(values: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise InvalidRepositoryDataError("steps_executed entries must be objects.")
        agent = value.get("agent", "")
        purpose = value.get("purpose", "")
        if not isinstance(agent, str) or not isinstance(purpose, str):
            raise InvalidRepositoryDataError("Agent-run step fields must be strings.")
        result.append({"agent": agent.strip(), "purpose": purpose.strip()})
    return result


def _agents(values: Sequence[str]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise InvalidRepositoryDataError("completed_agents must be a list of strings.")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise InvalidRepositoryDataError(
                "completed_agents entries must be strings."
            )
        normalized = value.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result
