"""Transport-independent interface for execution activity emitters.

LangGraph nodes depend on this small protocol instead of the SSE event bus.
That keeps normal graph execution transport-agnostic and makes node
instrumentation straightforward to test with a recording emitter.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IStreamEmitter(Protocol):
    """Typed interface implemented by execution activity emitters."""

    def emit_step_start(self, step_name: str, label: str) -> None: ...

    def emit_step_detail(
        self,
        step_name: str,
        detail: str,
        **metadata: Any,
    ) -> None: ...

    def emit_step_done(
        self,
        step_name: str,
        label: str,
        **metadata: Any,
    ) -> None: ...

    def emit_sources_found(self, count: int, titles: list[str]) -> None: ...

    def emit_plan(
        self,
        plan_type: str,
        steps: list[str],
        reasoning: str,
    ) -> None: ...

    def emit_final(self, response: dict[str, Any]) -> None: ...

    def emit_error(self, error: str) -> None: ...


class NullEmitter:
    """No-op strategy used by existing non-streaming graph executions."""

    def emit_step_start(self, *args: Any, **kwargs: Any) -> None:
        return None

    def emit_step_detail(self, *args: Any, **kwargs: Any) -> None:
        return None

    def emit_step_done(self, *args: Any, **kwargs: Any) -> None:
        return None

    def emit_sources_found(self, *args: Any, **kwargs: Any) -> None:
        return None

    def emit_plan(self, *args: Any, **kwargs: Any) -> None:
        return None

    def emit_final(self, *args: Any, **kwargs: Any) -> None:
        return None

    def emit_error(self, *args: Any, **kwargs: Any) -> None:
        return None


class FinalSuppressingEmitter:
    """Decorator that forwards activity while reserving final ownership.

    A graph used as a child pipeline may emit its own internal final response.
    Transport adapters that must return a different public response type wrap
    the request emitter with this decorator and emit their final event only
    after adapting the child result.
    """

    __slots__ = ("_delegate",)

    def __init__(self, delegate: IStreamEmitter) -> None:
        self._delegate = delegate

    def emit_step_start(self, step_name: str, label: str) -> None:
        self._delegate.emit_step_start(step_name, label)

    def emit_step_detail(
        self,
        step_name: str,
        detail: str,
        **metadata: Any,
    ) -> None:
        self._delegate.emit_step_detail(step_name, detail, **metadata)

    def emit_step_done(
        self,
        step_name: str,
        label: str,
        **metadata: Any,
    ) -> None:
        self._delegate.emit_step_done(step_name, label, **metadata)

    def emit_sources_found(self, count: int, titles: list[str]) -> None:
        self._delegate.emit_sources_found(count, titles)

    def emit_plan(
        self,
        plan_type: str,
        steps: list[str],
        reasoning: str,
    ) -> None:
        self._delegate.emit_plan(plan_type, steps, reasoning)

    def emit_final(self, response: dict[str, Any]) -> None:
        del response

    def emit_error(self, error: str) -> None:
        self._delegate.emit_error(error)
