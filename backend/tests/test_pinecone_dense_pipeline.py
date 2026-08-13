import pytest
from app.core.config import settings
from app.services.retrieval.legal_vector_store import LegalVectorStore, PineconeLegalRetriever

@pytest.mark.skipif(
    not settings.PINECONE_API_KEY or not settings.PINECONE_LEGAL_INDEX_HOST or not settings.JINA_API_KEY,
    reason="Pinecone API key, Pinecone index host, or Jina API key not set in environment"
)
def test_pinecone_dense_pipeline_integration():
    """
    Integration test to verify that the Pinecone dense semantic pipeline 
    is actually able to connect, embed the query via Jina, and return results.
    """
    store = LegalVectorStore()
    
    # Verify the dense index client is initialized
    assert store._dense_index is not None, "Dense index should be initialized"
    
    # 1. Test raw vector store search
    query = (
        "A vendor agrees to sell a commercial property to a buyer but subsequently negotiates "
        "to sell it to a third party for a higher price. The original buyer seeks an interim "
        "injunction to prevent the sale to the third party pending a specific performance suit. "
        "Based on Roberts v. Ratnayake, what legal standards must the buyer satisfy to obtain "
        "this equitable relief?"
    )
    documents = store.search_children(query=query, limit=5)
    
    # If the index is populated, it should return some documents
    assert isinstance(documents, list)
    if len(documents) > 0:
        doc = documents[0]
        assert hasattr(doc, "page_content")
        assert hasattr(doc, "metadata")
        assert doc.metadata.get("chunk_type") == "child"
        assert "point_id" in doc.metadata

    # 2. Test the LangChain retriever wrapper
    retriever = PineconeLegalRetriever(store=store, k=5)
    retrieved_docs = retriever.invoke(query)
    
    print("\n" + "="*50)
    print(f"DENSE QUERY: '{query}'")
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
