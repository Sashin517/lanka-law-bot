from __future__ import annotations

from unittest.mock import Mock, patch

from app.agents import shared


def test_shared_retrieval_is_not_initialized_during_import() -> None:
    assert isinstance(shared.retrieval_service, shared._LazyRetrievalService)


def test_shared_retrieval_is_initialized_on_first_search() -> None:
    configured_service = Mock()
    configured_service.search.return_value = ["result"]

    with patch.object(
        shared,
        "get_configured_retrieval_service",
        return_value=configured_service,
    ) as factory:
        result = shared.retrieval_service.search("question", top_k=3)

    assert result == ["result"]
    factory.assert_called_once_with()
    configured_service.search.assert_called_once_with("question", top_k=3)
