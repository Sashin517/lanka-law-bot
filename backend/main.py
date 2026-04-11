from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys
import os
from typing import Optional

# Add the src folder to the path so we can import your agent
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from agent import search_database

app = FastAPI(title="LankaLawBot API")

# --- CORS Permission Slip ---
# This allows your Next.js frontend to securely talk to this Python backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

# Define the format of the incoming request from Next.js

class LegalQuery(BaseModel):
    question: str
    doc_type: str | None = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None

@app.get("/")
def read_root():
    return {"status": "LankaLawBot Backend is running!"}

@app.post("/api/search")
def search_law(query: LegalQuery):
    # Pass the UI filters into your new agent function
    docs = search_database(query.question, query.doc_type, query.start_year)
    
    #Format the LangChain documents into JSON objects for React
    formatted_results = []
    for i, doc in enumerate(docs):
        # Extract the source filename from ChromaDB metadata (e.g., Year_1995_Act_21)
        source_name = doc.metadata.get("source", "Unknown Document").replace(".json", "")
        
        formatted_results.append({
            "id": i,
            "title": source_name.replace("_", " "), # Makes it readable: "Year 1995 Act 21"
            "subtitle": "Legal Precedent",
            "excerpt": doc.page_content[:250] + "...", # Send the first 250 characters as a preview
            "score": "High" # ChromaDB similarity score placeholder
        })
        
    return {"results": formatted_results}