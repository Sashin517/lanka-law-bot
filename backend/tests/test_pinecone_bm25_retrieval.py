from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(
        module_name,
        BACKEND_DIR / relative_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


legal_vector_store = _load_module(
    "legal_vector_store_under_test",
    "app/services/retrieval/legal_vector_store.py",
)
LegalVectorStore = legal_vector_store.LegalVectorStore


class _FakeBM25Match:
    id = "record-1"

    def to_dict(self) -> dict:
        return {
            "_id": "record-1",
            "_score": 0.42,
            "text": "The buyer may recover damages for breach of contract.",
            "chunk_id": "chunk-1",
            "parent_id": "parent-1",
            "chunk_type": "child",
            "source_filename": "contract.md",
            "year": 2003,
        }


class _FakeDocumentsClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(matches=[_FakeBM25Match()])


class _FakeBM25Index:
    def __init__(self) -> None:
        self.documents = _FakeDocumentsClient()


def test_search_children_bm25_uses_pinecone_fts_and_preserves_metadata():
    store = object.__new__(LegalVectorStore)
    store._bm25_index = _FakeBM25Index()
    store.bm25_namespace = "legal_corpus"

    documents = store.search_children_bm25(
        query="contract damages",
        limit=7,
        metadata_filters={"year": {"$eq": 2003}},
    )

    call = store._bm25_index.documents.calls[0]
    assert call["namespace"] == "legal_corpus"
    assert call["top_k"] == 7
    assert call["score_by"] == [
        {"type": "text", "field": "text", "query": "contract damages"}
    ]
    assert call["include_fields"] == ["*"]
    assert call["filter"] == {
        "chunk_type": {"$eq": "child"},
        "year": {"$eq": 2003},
    }

    assert len(documents) == 1
    assert documents[0].page_content == (
        "The buyer may recover damages for breach of contract."
    )
    assert documents[0].metadata["point_id"] == "record-1"
    assert documents[0].metadata["chunk_id"] == "chunk-1"
    assert documents[0].metadata["parent_id"] == "parent-1"
    assert documents[0].metadata["source_filename"] == "contract.md"
    assert "_score" not in documents[0].metadata


def test_retrieval_service_no_longer_imports_or_builds_local_bm25():
    source = (BACKEND_DIR / "app/services/retrieval/retrieval_service.py").read_text(
        encoding="utf-8"
    )

    assert "from langchain_community.retrievers import BM25Retriever" not in source
    assert "BM25Retriever.from_documents" not in source
    assert "load_children_for_bm25" not in source
    assert "PineconeLegalBM25Retriever" in source
