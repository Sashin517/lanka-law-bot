import os
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_classic.retrievers.document_compressors.cross_encoder_rerank import CrossEncoderReranker
from langchain_core.documents import Document

def main():
    print("Initializing Cross-Encoder model...")
    model = HuggingFaceCrossEncoder(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")
    
    print("Setting up CrossEncoderReranker...")
    compressor = CrossEncoderReranker(model=model, top_n=3)
    
    # Create some dummy documents
    docs = [
        Document(page_content="The rules regarding tenancy termination require a notice in writing.", metadata={"id": 1, "title": "Doc A"}),
        Document(page_content="Apples and oranges are fruits that grow on trees.", metadata={"id": 2, "title": "Doc B"}),
        Document(page_content="Tenancy agreements are legally binding contracts between landlord and tenant.", metadata={"id": 3, "title": "Doc C"}),
    ]
    
    query = "What are the rules regarding tenancy termination?"
    print(f"Query: '{query}'\n")
    
    print("Compressing documents...")
    compressed_docs = compressor.compress_documents(docs, query)
    
    print("\n--- Reranked Documents ---")
    for i, doc in enumerate(compressed_docs):
        print(f"Result #{i+1}:")
        print(f"  Content: {doc.page_content}")
        print(f"  Metadata keys: {list(doc.metadata.keys())}")
        print(f"  Metadata: {doc.metadata}")
        print()

if __name__ == "__main__":
    main()
