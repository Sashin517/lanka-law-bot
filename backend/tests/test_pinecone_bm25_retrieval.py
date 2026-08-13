from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from langchain_core.documents import Document


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(
        module_name,
        BACKEND_DIR / relative_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


legal_vector_store = _load_module(
    "legal_vector_store_under_test",
    "app/services/retrieval/legal_vector_store.py",
)
LegalVectorStore = legal_vector_store.LegalVectorStore
PineconeLegalHybridRetriever = legal_vector_store.PineconeLegalHybridRetriever
retrieval_service = _load_module(
    "retrieval_service_under_test",
    "app/services/retrieval/retrieval_service.py",
)
RetrievalService = retrieval_service.RetrievalService


class _FakeDocument:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def to_dict(self) -> dict:
        return dict(self.payload)


class _FakeDocumentsClient:
    def __init__(self) -> None:
        self.search_calls: list[dict] = []
        self.fetch_calls: list[dict] = []

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return SimpleNamespace(
            matches=[
                _FakeDocument(
                    {
                        "_id": "chunk-1",
                        "_score": 0.42,
                        "text": "The buyer may recover damages for breach.",
                        "title": "Sale of Goods Ordinance",
                        "citation": "Ordinance No. 11 of 1896",
                        "section_label": "Section 51",
                        "chunk_id": "chunk-1",
                        "parent_id": "parent-1",
                        "chunk_type": "child",
                        "year": 1896,
                    }
                )
            ]
        )

    def fetch(self, **kwargs):
        self.fetch_calls.append(kwargs)
        return SimpleNamespace(
            documents={
                "parent-1": _FakeDocument(
                    {
                        "_id": "parent-1",
                        "text": "Parent statutory context.",
                        "chunk_id": "parent-1",
                        "chunk_type": "parent",
                        "title": "Sale of Goods Ordinance",
                    }
                )
            }
        )


class _FakeIndex:
    def __init__(self) -> None:
        self.documents = _FakeDocumentsClient()


class _FakeDenseIndex:
    def __init__(self) -> None:
        self.fetch_calls: list[dict] = []

    def fetch(self, **kwargs):
        self.fetch_calls.append(kwargs)
        return SimpleNamespace(vectors={})


def test_bm25_search_uses_preview_index_and_text_field():
    store = object.__new__(LegalVectorStore)
    store._bm25_index = _FakeIndex()
    store.bm25_namespace = "legal_corpus_release"

    documents = store.search_children_bm25(
        query="section 51 damages",
        limit=7,
        metadata_filters={"year": {"$eq": 1896}},
    )

    call = store._bm25_index.documents.search_calls[0]
    assert call["namespace"] == "legal_corpus_release"
    assert call["top_k"] == 7
    assert call["score_by"] == [
        {"type": "text", "field": "text", "query": "section 51 damages"},
    ]
    assert call["filter"] == {
        "$and": [
            {"chunk_type": {"$eq": "child"}},
            {"year": {"$eq": 1896}},
        ]
    }
    assert "dense_vector" not in call["include_fields"]
    assert documents[0].page_content == "The buyer may recover damages for breach."
    assert documents[0].metadata["point_id"] == "chunk-1"
    assert documents[0].metadata["retrieval_channel"] == "bm25"
    assert documents[0].metadata["retrieval_score"] == 0.42


def test_parent_is_fetched_from_bm25_when_dense_misses():
    store = object.__new__(LegalVectorStore)
    store._dense_index = _FakeDenseIndex()
    store.dense_namespace = "legal_corpus_release"
    store._bm25_index = _FakeIndex()
    store.bm25_namespace = "legal_corpus_release"

    parent = store.fetch_parent("parent-1")

    assert store._dense_index.fetch_calls[0]["ids"] == ["parent-1"]
    assert store._bm25_index.documents.fetch_calls[0]["ids"] == ["parent-1"]
    assert parent is not None
    assert parent.page_content == "Parent statutory context."
    assert parent.metadata["chunk_type"] == "parent"


class _HybridStore(LegalVectorStore):
    def __init__(self) -> None:
        # Avoid remote client construction; search methods are fully stubbed.
        pass

    def search_children(self, *_args, **_kwargs):
        return [
            Document(
                page_content="shared",
                metadata={
                    "chunk_id": "shared-id",
                    "retrieval_channel": "dense",
                    "retrieval_score": 0.9,
                },
            ),
            Document(page_content="dense", metadata={"chunk_id": "dense-id"}),
        ]

    def search_children_bm25(self, *_args, **_kwargs):
        return [
            Document(
                page_content="shared",
                metadata={
                    "chunk_id": "shared-id",
                    "retrieval_channel": "bm25",
                    "retrieval_score": 12.0,
                },
            ),
            Document(page_content="lexical", metadata={"chunk_id": "lexical-id"}),
        ]


def test_hybrid_retriever_fuses_by_chunk_id_and_preserves_channel_diagnostics():
    retriever = PineconeLegalHybridRetriever(
        store=_HybridStore(),
        k=5,
        dense_weight=0.6,
        sparse_weight=0.4,
    )

    documents = retriever._get_relevant_documents("damages", run_manager=None)  # type: ignore[arg-type]

    assert documents[0].metadata["chunk_id"] == "shared-id"
    assert set(documents[0].metadata["retrieval_channels"]) == {"dense", "bm25"}
    assert documents[0].metadata["rrf_score"] > documents[1].metadata["rrf_score"]


def test_retrieval_service_uses_hybrid_retriever_not_ensemble():
    source = (BACKEND_DIR / "app/services/retrieval/retrieval_service.py").read_text(
        encoding="utf-8"
    )
    assert "EnsembleRetriever" not in source
    assert "PineconeLegalHybridRetriever" in source
    assert "self._reranked_retriever" not in source


def test_route_constraints_become_year_only_pre_scoring_filters():
    assert RetrievalService._build_pinecone_filter([1896], None) == {
        "year": {"$eq": 1896}
    }
    # Act-name filters are intentionally excluded from Pinecone pre-filters
    # because partial titles do not match full statutory titles under $eq.
    assert RetrievalService._build_pinecone_filter(None, ["Sale of Goods Ordinance"]) is None
    assert RetrievalService._build_pinecone_filter(
        [1896, 2007], ["Sale of Goods Ordinance", "Companies Act"]
    ) == {"year": {"$in": [1896, 2007]}}


def test_post_filter_combines_constraints_and_falls_back_when_empty():
    candidates = [
        Document(
            page_content="match",
            metadata={"year": 1896, "title": "Sale of Goods Ordinance"},
        ),
        Document(
            page_content="wrong title",
            metadata={"year": 1896, "title": "Companies Act"},
        ),
        Document(
            page_content="missing year",
            metadata={"title": "Sale of Goods Ordinance"},
        ),
    ]

    filtered = RetrievalService._post_filter_metadata(
        candidates, [1896], ["Sale of Goods Ordinance"]
    )

    assert [doc.page_content for doc in filtered] == ["match"]
    # When nothing matches, current policy falls back to the unfiltered candidates.
    assert RetrievalService._post_filter_metadata(candidates, [2025], None) == candidates
