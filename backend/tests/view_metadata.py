import os
import json
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

def main():
    TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
    BACKEND_DIR = os.path.dirname(TESTS_DIR)
    CHROMA_PATH = os.path.join(BACKEND_DIR, "database", "chroma_db")

    if not os.path.exists(CHROMA_PATH):
        print(f"Error: Chroma database not found at {CHROMA_PATH}")
        return

    print("Loading vector database...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)

    print("Fetching a sample of chunks to analyze metadata...")
    
    # Fetch a large batch to find all possible metadata keys
    results = db.get(include=["metadatas", "documents"], limit=5000, offset=0)
    metadatas = results.get("metadatas", [])
    documents = results.get("documents", [])
    
    if not metadatas:
        print("Database is empty.")
        return

    # 1. Find all unique metadata keys across the chunks
    all_keys = set()
    for meta in metadatas:
        if meta:
            all_keys.update(meta.keys())

    print("\n" + "=" * 50)
    print("METADATA SCHEMA (All keys found in the database):")
    print("=" * 50)
    for key in sorted(all_keys):
        print(f"- {key}")

    # 2. Print a detailed sample of the first 3 chunks
    print("\n" + "=" * 50)
    print("SAMPLE CHUNKS (First 3):")
    print("=" * 50)
    
    for i in range(min(3, len(metadatas))):
        print(f"\n--- Chunk {i+1} ---")
        print("METADATA:")
        # Print metadata as nicely formatted JSON
        print(json.dumps(metadatas[i], indent=2))
        
        print("\nTEXT EXCERPT:")
        # Print the first 200 characters of the actual text
        doc_text = documents[i] if documents[i] else ""
        print(f"{doc_text[:200].replace(chr(10), ' ')}...") # Replacing newlines with spaces for clean printing

if __name__ == "__main__":
    main()
