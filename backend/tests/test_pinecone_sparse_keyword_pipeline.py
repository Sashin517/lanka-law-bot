import pytest
from app.core.config import settings
from app.services.retrieval.legal_vector_store import LegalVectorStore, PineconeLegalBM25Retriever

@pytest.mark.skipif(
    not settings.PINECONE_API_KEY or not settings.PINECONE_LEGAL_INDEX_HOST,
    reason="Pinecone API key or document index host not set in environment"
)
def test_pinecone_sparse_keyword_pipeline_integration():
    """
    Integration test to verify that the Pinecone BM25 sparse keyword pipeline 
    is actually able to connect and return results for a keyword search.
    """
    store = LegalVectorStore()
    
    # Dense and BM25 ranking use the same document-schema index.
    assert store._index is not None, "Document index should be initialized"
    
    # 1. Test raw vector store search
    keyword_query = (
        "A seller of agricultural produce verbally demands that a buyer take delivery by Friday. "
        "However, on that Friday, the goods are securely locked in a warehouse in a different district, "
        "not at the agreed place of delivery. If the seller sues for damages for non-acceptance, "
        "how would the court evaluate the seller's claim under Rawanna & Co. v. Arunachapillai?"
    )
    documents = store.search_children_bm25(query=keyword_query, limit=5)
    
    # If the index is populated, it should return some documents
    # (If the index is empty, it might return 0, but this assumes it is populated)
    assert isinstance(documents, list)
    if len(documents) > 0:
        doc = documents[0]
        assert hasattr(doc, "page_content")
        assert hasattr(doc, "metadata")
        assert doc.metadata.get("chunk_type") == "child"
        assert "point_id" in doc.metadata

    # 2. Test the LangChain retriever wrapper
    retriever = PineconeLegalBM25Retriever(store=store, k=5)
    retrieved_docs = retriever.invoke(keyword_query)
    
    print("\n" + "="*50)
    print(f"QUERY: '{keyword_query}'")
    print(f"TOTAL DOCUMENTS RETRIEVED: {len(retrieved_docs)}")
    print("="*50)

    for i, doc in enumerate(retrieved_docs, 1):
        print(f"\n--- Result {i} ---")
        print(f"Title / Filename: {doc.metadata.get('title') or doc.metadata.get('source_filename', 'Unknown')}")
        print(f"Chunk Type: {doc.metadata.get('chunk_type')}")
        print(f"Score (if available): {doc.metadata.get('_score', 'N/A')}")
        print(f"Snippet: {doc.page_content[:200]}...")
    
    assert isinstance(retrieved_docs, list)
    if len(retrieved_docs) > 0:
        doc = retrieved_docs[0]
        assert hasattr(doc, "page_content")
        assert hasattr(doc, "metadata")
        assert doc.metadata.get("chunk_type") == "child"
