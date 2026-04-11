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
    doc_type: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None

@app.get("/")
def read_root():
    return {"status": "LankaLawBot Backend is running!"}

@app.post("/api/search")
def search_law(query: LegalQuery):
    # Pass the question to the exact script you just ran
    result_text = search_database(query.question)
    
    if not result_text:
        return {"answer": "I could not find any relevant legal precedents for that question."}
        
    return {"answer": result_text}