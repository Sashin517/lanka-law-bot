import logging
from app.services.retrieval_service import RetrievalService

# Set up logging to see the internal info logs
logging.basicConfig(level=logging.INFO)

print("Initializing Retrieval Service (this may take a few seconds to load models)...")
retrieval_service = RetrievalService()

print("\n--- Testing Retrieval Pipeline ---")
query = "What are the rules regarding tenancy termination?"
print(f"Query: {query}\n")

# Execute hybrid search
results = retrieval_service.search(query=query, top_k=3, expand_parents=False)

if not results:
    print("No results found. The database might be empty.")
else:
    for i, result in enumerate(results):
        child_chunk = result["child"]
        metadata = result["metadata"]
        
        # The Cross-Encoder Reranker injects a 'relevance_score' into the metadata if it worked
        rerank_score = metadata.get("relevance_score", "N/A")
        
        print(f"Result #{i + 1}:")
        print(f"  Source Document: {metadata.get('title') or metadata.get('source', 'Unknown')}")
        print(f"  Cross-Encoder Score: {rerank_score}")
        print(f"  Text Snippet: {child_chunk.page_content[:150]}...\n")

print("--- Pipeline Diagnostics ---")
if retrieval_service._hybrid_retriever:
    print("[SUCCESS] BM25 & Hybrid Search are ACTIVE.")
else:
    print("[FAILED] BM25 is DISABLED (usually because no 'child' chunks were found).")

if retrieval_service._reranked_retriever:
    print("[SUCCESS] Cross-Encoder Reranker is ACTIVE.")
else:
    print("[FAILED] Cross-Encoder Reranker is DISABLED.")
