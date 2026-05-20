# LankaLawBot - Generative AI Legal Assistant

## 🎯 Overview

A Generative AI Agentic Framework for Personalized Legal Drafting and Case Intelligence within the Sri Lankan Jurisdiction. Built with a modern Next.js frontend, a lightning-fast FastAPI backend, and powered by LangChain, HuggingFace, and ChromaDB for secure, local Retrieval-Augmented Generation (RAG).

## 📦 Project Architecture

### 1. **Frontend (`/frontend`)**

- `src/app/page.tsx` - Main interactive chat UI built with React and Tailwind CSS.
- `package.json` - Node dependencies (Next.js, React).

### 2. **Backend (`/backend`)**

- `main.py` - FastAPI server handling CORS and API routing.
- `src/agent.py` - Core RAG logic connecting the query to the vector database.
- `requirements.txt` - Python dependencies (LangChain, ChromaDB, FastAPI, etc.).

### 3. **Data & Storage**

- `database/chroma_db/` - Local vector database containing embedded Sri Lankan legal acts.
- `data/` - Raw, cleanly named JSON legal documents (e.g., `Year_1995_Act_21.json`).

---

## 🚀 How to Run Locally

To run this application, you need to start both the Python backend server and the Next.js frontend server simultaneously in two separate terminal windows.

### 🗄️ Database Setup

The Vector Database (`chroma_db`) is ignored by Git to keep the repository lightweight. To run this project locally, you must download the pre-built database.

1. Download the `chroma_db.zip` file from our shared team drive: [Download file](https://drive.google.com/drive/folders/1y-I_gl9o1FnFu3rA2kLYzOMS9pakjz6O?usp=drive_link)
2. Extract the zip file.
3. Place the extracted `chroma_db` folder directly inside the `backend/database/` directory.
4. Your folder structure should look like this: `backend/database/chroma_db/`

### Step 1: Start the Backend (FastAPI + AI Engine)

1. Open a terminal and navigate to the backend folder:
   ```bash
   cd backend
   ```
2. Activate your Python virtual environment (Ensure you are using Python 3.12):
   - **Windows:** `venv\Scripts\activate`
   - **Mac/Linux:** `source venv/bin/activate`
3. Start the FastAPI server:

   ```bash
   uvicorn main:app
   uvicorn main:app --reload
   ```

   _The backend is now running on `http://127.0.0.1:8000`._

### Step 2: Start the Frontend (Next.js UI)

1. Open a **second** new terminal window and navigate to the frontend folder:
   ```bash
   cd frontend
   ```
2. Install dependencies (only needed the very first time):
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```
   _The frontend is now running on `http://localhost:3000`._

### Step 3: Access the Application

Open your web browser and navigate to **`http://localhost:3000`**. You can now type a legal query and the UI will communicate directly with your local AI backend.

---

## 🔄 Complete User Flow

### 1. **Query Input**

- User navigates to the web interface.
- Enters a natural language legal question (e.g., _"What are the rules regarding tenancy termination?"_).

### 2. **API Communication**

- Next.js sends a secure `POST` request containing the query to the FastAPI backend (`/api/search`).
- CORS middleware ensures secure cross-origin communication between port 3000 and port 8000.

### 3. **Semantic Search (RAG)**

- The FastAPI server passes the query to the LangChain agent.
- `all-MiniLM-L6-v2` converts the user's text into mathematical vectors.
- ChromaDB performs a similarity search against the local vector database of Sri Lankan law.

### 4. **Response Delivery**

- The most relevant legal chunks are retrieved.
- The source document metadata (e.g., `Year_1999_Act_...`) and context are streamed back to the Next.js frontend.
- The UI gracefully animates the response into view for the user.

---

## 🎨 Key Features

### ✅ Local & Private AI Processing

- Uses HuggingFace open-source embeddings running entirely on your local machine.
- No legal queries are sent to external paid APIs (like OpenAI), ensuring data privacy and zero recurring costs.

### ✅ Semantic Vector Search

- Goes beyond basic keyword matching. The AI understands the _meaning_ of the question and finds relevant laws even if exact vocabulary isn't used.

### ✅ Meaningful Citations

- Custom data processing pipeline ensures raw data is parsed and formatted so the AI can provide exact references to the Year and Act Number.

### ✅ Modern, Responsive UI

- Built with Tailwind CSS.
- Features loading states, clean typography, and a mobile-responsive design for practitioners on the go.

---

## 🔧 Tech Stack Reference

- **Frontend:** Next.js 14, React, Tailwind CSS, TypeScript
- **Backend:** Python 3.12, FastAPI, Uvicorn, Pydantic
- **AI & Machine Learning:** LangChain, HuggingFace (`all-MiniLM-L6-v2`), Sentence-Transformers, Numpy
- **Database:** ChromaDB (Local SQLite Vector Storage)

---

## 🚨 Common Issues & Solutions

### Issue: "Could not connect to the LankaLawBot backend"

**Solution**: Ensure your FastAPI server is running in a separate terminal. Check that CORS is properly configured in `main.py` to allow `http://localhost:3000`.

### Issue: "metadata-generation-failed" during `pip install`

**Solution**: This happens when using Python 3.13 due to missing C++ compilers for Numpy. Ensure your virtual environment is explicitly built using **Python 3.12**.

### Issue: FastAPI returns "No results found"

**Solution**: Verify that your `database/chroma_db` folder contains the compiled database files and is located in the correct directory relative to `agent.py`.

---

## 📈 Future Enhancements

1. **LLM Generation Layer**
   - Integrate a local LLM (like Llama 3 or Mistral) to summarize the retrieved legal chunks into human-readable advice, rather than just returning the raw text.
2. **Cloud Deployment**
   - Host the Next.js frontend on Vercel.
   - Deploy the FastAPI backend and ChromaDB on a DigitalOcean VPS for 24/7 accessibility.
3. **Drafting Capabilities**
   - Add features allowing the bot to generate boilerplate legal templates based on the retrieved acts.

---

## 📄 License

Created by Prime Minds. All rights reserved.
