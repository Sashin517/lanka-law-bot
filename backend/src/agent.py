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

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH = os.path.join(BASE_DIR, "database", "chroma_db")

# Initialize Embeddings and Database instance
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)

def search_database(question: str, doc_type: str = None, start_year: int = None):
    # 1. Build the filter dictionary dynamically based on UI inputs
    filter_dict = {}
    
    if doc_type:
        filter_dict["type"] = doc_type
    if start_year:
        filter_dict["year"] = {"$gte": start_year} # $gte means "greater than or equal to"

    # 2. Pass the exact filters into the Chroma search
    # If no filters are provided, it falls back to a pure semantic search across all docs
    retriever = db.as_retriever(
        search_type="similarity",
        search_kwargs={
            "k": 5, 
            "filter": filter_dict if filter_dict else None
        }
    )
    
    docs = retriever.invoke(question)
    return docs

if __name__ == "__main__":
    # Test a query with hypothetical UI filters applied
    test_query = "What are the rules regarding the termination of a tenancy agreement?"
    
    print(f"Searching for: '{test_query}' (Type: Act, Since: 1990)")
    results = search_database(test_query, doc_type="Act", start_year=1990)
    
    for idx, doc in enumerate(results):
        print(f"\n--- Result {idx + 1} ---")
        print(f"Source: {doc.metadata.get('source', 'Unknown')}")
        print(doc.page_content[:200] + "...")