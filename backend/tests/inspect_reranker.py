import inspect
from langchain_classic.retrievers.document_compressors.cross_encoder_rerank import CrossEncoderReranker

def main():
    print("Inspecting CrossEncoderReranker class...")
    
    # 1. Print class source code or method source code
    try:
        source = inspect.getsource(CrossEncoderReranker.compress_documents)
        print("\n--- Source of CrossEncoderReranker.compress_documents ---")
        print(source)
    except Exception as e:
        print(f"Error inspecting compress_documents method: {e}")
        
    try:
        init_source = inspect.getsource(CrossEncoderReranker.__init__)
        print("\n--- Source of CrossEncoderReranker.__init__ ---")
        print(init_source)
    except Exception as e:
        print(f"Error inspecting __init__ method: {e}")

if __name__ == "__main__":
    main()
