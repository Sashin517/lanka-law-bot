"""Lazy public exports for document-ingestion services.

Keeping package import side-effect free avoids loading LLM and Neo4j clients in
API workers that only need file storage or parsing.
"""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "DocumentParser": "app.services.ingestion.document_parser",
    "ParsedDocument": "app.services.ingestion.document_parser",
    "DocumentStorage": "app.services.ingestion.document_storage",
    "StoredFile": "app.services.ingestion.document_storage",
    "LegalDocumentChunker": "app.services.ingestion.legal_chunker",
    "ChunkingDocumentContext": "app.services.ingestion.legal_chunker",
    "LegalChunk": "app.services.ingestion.legal_chunker",
    "ChunkSet": "app.services.ingestion.legal_chunker",
    "IngestionJobService": "app.services.ingestion.ingestion_jobs",
    "Neo4jLLMEntityExtractor": ("app.services.ingestion.neo4j_llm_entity_extractor"),
    "Neo4jGraphBuilder": "app.services.ingestion.neo4j_graph_builder",
    "slugify": "app.services.ingestion.neo4j_graph_builder",
    "slugify_section": "app.services.ingestion.neo4j_graph_builder",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
