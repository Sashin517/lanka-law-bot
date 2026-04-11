import os
import numpy as np
import langchain_community.utils.math as lc_math

# Apply custom patch for math evaluation
def patched_cosine_similarity(X, Y):
    X = np.array(X, dtype=np.float32)
    Y = np.array(Y, dtype=np.float32)
    X_norm = X / np.linalg.norm(X, axis=1, keepdims=True)
    Y_norm = Y / np.linalg.norm(Y, axis=1, keepdims=True)
    return np.dot(X_norm, Y_norm.T)

lc_math.cosine_similarity = patched_cosine_similarity

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH = os.path.join(BASE_DIR, "database", "chroma_db")

def search_database(query: str):
    print("Connecting to LankaLawBot Database...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
    
    print(f"Searching for: '{query}'")
    results = db.similarity_search(query, k=2)
    
    if not results:
        print("No results found.")
        return None

    top_match = results[0]
    print(f"\n--- Source: {top_match.metadata.get('source', 'Unknown')} ---")
    print(f"{top_match.page_content[:300]}...\n")
    
    # Calculate score
    query_vec = np.array(embeddings.embed_query(query))
    doc_vec = np.array(embeddings.embed_query(top_match.page_content))
    cosine_sim = np.dot(query_vec, doc_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(doc_vec))
    distance_score = 1 - cosine_sim
    
    print(f"Distance Score: {distance_score:.4f} (Closer to 0 = highly relevant)")
    return top_match.page_content

if __name__ == "__main__":
    test_query = "What are the rules regarding the termination of a tenancy agreement?"
    search_database(test_query)