# LankaLawBot - Generative AI Legal Assistant

## Overview

A Generative AI Agentic Framework for Personalized Legal Drafting and Case Intelligence within the Sri Lankan Jurisdiction. Built with a modern Next.js frontend, a FastAPI backend, and powered by LangGraph, LangChain, HuggingFace, Pinecone, and Neo4j for secure, multi-agent Retrieval-Augmented Generation (RAG) and Graph RAG.

## Project Architecture

### 1. Frontend (`/frontend`)
- `src/app/page.tsx` - Main interactive chat interface built with React and Tailwind CSS.
- `package.json` - Node dependencies (Next.js, React).

### 2. Backend (`/backend`)
- `main.py` - FastAPI server handling CORS, API routing, and automated database orchestration.
- `app/agents/` - LangGraph multi-agent architecture including Reasoning and Drafting nodes.
- `app/services/retrieval/` - Hybrid retrieval pipelines integrating Pinecone (Vector/BM25) and Neo4j (Graph RAG).
- `requirements.txt` - Python dependencies (LangChain, FastAPI, Neo4j, etc.).

### 3. Data & Storage
- **Vector Database (Pinecone / ChromaDB):** Stores embedded Sri Lankan legal acts for semantic and keyword retrieval.
- **Graph Database (Neo4j):** Stores relational legal data (e.g., amendments, citations, repeals) for complex reasoning and context injection.
- `data/` - Raw, cleanly named JSON legal documents.

---

## How to Run Locally

To run this application, you need to start both the Python backend server and the Next.js frontend server. The backend will automatically orchestrate the Graph database setup using Docker.

### Prerequisites
- Python 3.12
- Node.js
- Docker (Required for the automated Neo4j graph database)

### Step 1: Start the Backend (FastAPI + AI Engine)

1. Open a terminal and navigate to the backend folder:
   ```bash
   cd backend
   ```
2. Activate your Python virtual environment:
   - **Windows:** `venv\Scripts\activate`
   - **Mac/Linux:** `source venv/bin/activate`
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure Environment Variables:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and add your valid Google Gemini, Pinecone, and LangSmith API keys.
5. Start the FastAPI server:  
   ```bash
   uvicorn main:app --reload
   ```
   *Note: Upon startup, the backend will automatically use Docker to download and run a Neo4j instance, and idempotently populate the graph database with legal relationships.*
   
   The backend will run on `http://127.0.0.1:8000`.

### Step 2: Start the Frontend (Next.js UI)

1. Open a second terminal window and navigate to the frontend folder:
   ```bash
   cd frontend
   ```
2. Install dependencies (only needed the first time):
   ```bash
   npm install
   ```
3. Configure Environment Variables:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and add your Firebase project credentials.
4. Start the development server:
   ```bash
   npm run dev
   ```
   The frontend will run on `http://localhost:3000`.

### Step 3: Access the Application

Open your web browser and navigate to `http://localhost:3000`. You can now submit legal queries and interact with the AI assistant.

---

## Complete User Flow

### 1. Query Input
- The user navigates to the web interface.
- Enters a natural language legal question or a request for a drafted document.

### 2. Multi-Agent Routing (LangGraph)
- Next.js sends a secure request to the FastAPI backend.
- The router agent analyzes the intent and routes the query to the appropriate worker agent (e.g., Reasoning Agent or Drafting Agent).

### 3. Hybrid RAG & Graph RAG Retrieval
- **Semantic & Sparse Search:** The query is converted into vectors and searched against the vector database (Pinecone/ChromaDB) to retrieve the most semantically relevant legal chunks and exact keyword matches (BM25).
- **Relational Graph Search:** Simultaneously, entities are extracted from the query and queried against Neo4j to find relational context (e.g., if Act A was amended by Act B).
- The combined context is verified and assembled.

### 4. Response Generation & Delivery
- The assigned agent generates a highly accurate, legally grounded response or drafted document.
- Source document metadata and contextual citations are streamed back to the Next.js frontend for transparent referencing.

---

## Key Features

### Agentic Workflow (LangGraph)
- Utilizes specialized autonomous agents to handle different legal tasks, such as deep legal reasoning (IRAC analysis) and template-aware legal drafting.

### Advanced Retrieval Augmented Generation (RAG)
- **Hybrid Search:** Combines dense vector embeddings with sparse BM25 keyword matching for maximum retrieval accuracy.
- **Graph RAG:** Leverages Neo4j to trace explicit relationships between legal documents, preventing the AI from referencing outdated or repealed laws.

### Local & Private AI Processing Capabilities
- Capable of using local HuggingFace embeddings, ensuring data privacy and reducing reliance on external APIs.

### Meaningful Citations
- A custom data processing pipeline ensures raw data is parsed and formatted so the AI can provide exact references to the Year and Act Number.

---

## Tech Stack Reference

- **Frontend:** Next.js 14, React, Tailwind CSS, TypeScript
- **Backend:** Python 3.12, FastAPI, Uvicorn, Pydantic
- **AI & Machine Learning:** LangChain, LangGraph, HuggingFace, Google Gemini
- **Databases:** Pinecone / ChromaDB (Vector Storage), Neo4j (Graph Storage)

---

## Common Issues & Solutions

### Issue: "Could not connect to the LankaLawBot backend"
**Solution:** Ensure your FastAPI server is running in a separate terminal. Check that CORS is properly configured in `main.py` to allow `http://localhost:3000`.

### Issue: "ModuleNotFoundError: No module named 'langchain_neo4j'"
**Solution:** Ensure you have activated your virtual environment and installed the latest backend requirements (`pip install -r requirements.txt`).

### Issue: Backend startup hangs indefinitely
**Solution:** The backend automatically pulls the Neo4j Docker image on its first run. Depending on your internet speed, this may take several minutes. Ensure Docker is running.

