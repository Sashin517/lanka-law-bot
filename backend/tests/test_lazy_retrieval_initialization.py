from __future__ import annotations

from unittest.mock import Mock, patch

from app.agents import shared


def test_shared_retrieval_is_eagerly_configured_at_import() -> None:
    """Agent nodes share one eagerly constructed retrieval singleton."""
    assert shared.retrieval_service is not None
    assert hasattr(shared.retrieval_service, "search")


def test_get_configured_retrieval_service_routes_by_backend() -> None:
    neo4j_service = Mock(name="neo4j-retrieval")
    pinecone_service = Mock(name="pinecone-retrieval")

    with (
        patch.object(shared.settings, "RETRIEVAL_BACKEND", "neo4j"),
        patch.object(
            shared, "get_neo4j_retrieval_service", return_value=neo4j_service
        ) as neo4j_factory,
        patch.object(shared, "RetrievalService", return_value=pinecone_service) as pinecone_factory,
    ):
        selected = shared.get_configured_retrieval_service()

    assert selected is neo4j_service
    neo4j_factory.assert_called_once_with()
    pinecone_factory.assert_not_called()
