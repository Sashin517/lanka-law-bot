import os
import json
import shutil
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data")
CHROMA_PATH = os.path.join(BASE_DIR, "database", "chroma_db")

def build_vector_store():
    print("Starting Data Processing Pipeline...")
    documents = []
    
    # 1. Load Documents
    for file in os.listdir(DATA_PATH):
        if file.endswith(".json"):
            with open(os.path.join(DATA_PATH, file), 'r', encoding='utf-8') as f:
                data = json.load(f)
                full_text = ""
                if isinstance(data, list):
                    for block in data:
                        if 'text' in block:
                            full_text += block['text'] + "\n"
                
                if full_text.strip():
                    documents.append(Document(page_content=full_text, metadata={"source": file}))
                    
    print(f"Loaded {len(documents)} Acts.")

    # 2. Split Text
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=300)
    chunks = text_splitter.split_documents(documents)
    print(f"Split into {len(chunks)} searchable chunks.")

    # 3. Save to Chroma
    if os.path.exists(CHROMA_PATH):
        shutil.rmtree(CHROMA_PATH)

    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    Chroma.from_documents(documents=chunks, embedding=embeddings, persist_directory=CHROMA_PATH)
    
    print(f"SUCCESS! Database built locally at {CHROMA_PATH}")

if __name__ == "__main__":
    build_vector_store()