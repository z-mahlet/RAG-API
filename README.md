# Universal RAG Backend API

A small Retrieval-Augmented Generation (RAG) application. It reads text and PDF documents from `data/`, splits them into overlapping chunks, embeds them with Google Gemini, and stores the vectors in a local ChromaDB database. The FastAPI chat endpoint retrieves relevant chunks and asks Gemini to answer using that context.

## Features

- Ingest `.txt` and `.pdf` files from `data/`
- Gemini embeddings and grounded response generation
- Persistent local ChromaDB storage
- FastAPI endpoints for health checks and chat
- A simple browser chat widget served at `/`

## Requirements

- Python 3.12 recommended
- A Google Gemini API key with access to the configured embedding and generation models

## Setup (Windows PowerShell)

From the project directory:

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create a `.env` file in the project root. Each setting must be on its own `NAME=value` line:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
EMBEDDING_MODEL=gemini-embedding-001
LLM_MODEL=gemini-3.8-flash
CHROMA_PERSIST_DIR=./db
COLLECTION_NAME=knowledge_base
```

Replace the placeholder with your own Gemini API key. Keep `.env` private; it is excluded from Git. Environment values in `.env` override the defaults in `config.py`. If a model is unavailable to your API key, set `EMBEDDING_MODEL` or `LLM_MODEL` to a model available to your account.

## Add and ingest documents

Place `.txt` and/or `.pdf` files in the `data/` directory, then run:

```powershell
python ingest.py
```

The script extracts text, splits it into 60-word chunks with 15 words of overlap, creates Gemini embeddings, and upserts the chunks into the configured ChromaDB collection in `db/`. Run ingestion again after adding or updating documents.

## Start the API

From the project root, with the virtual environment active:

```powershell
python -m uvicorn main:app --reload
```

Open these URLs in a browser:

- Chat widget: <http://127.0.0.1:8000/>
- Health check: <http://127.0.0.1:8000/health>
- Interactive API docs: <http://127.0.0.1:8000/docs>

The health endpoint reports the collection name and number of indexed records. The API server must be running to use the widget or send chat requests.

## Chat API

`POST /api/chat` accepts a JSON body with a non-empty `message` and optional `top_k` value from 1 to 10 (default: 3).

Example request in PowerShell:

```powershell
$body = @{
    message = "What is the company policy on remote work?"
    top_k = 2
} | ConvertTo-Json -Compress

Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/api/chat" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

The response contains a `reply` and a `sources` array with the retrieved document chunks and their metadata. The assistant is instructed to say when the indexed context does not contain enough information to answer.

## Run integration checks

Start the API in one terminal, then run in another terminal with the virtual environment active:

```powershell
python test_suite.py
```

These checks call the running API and Gemini, so they require an available Gemini API key, indexed documents, and a working network connection.

## Project layout

```text
config.py          Environment and model settings
ingest.py          Document extraction, chunking, embedding, and indexing
main.py            FastAPI application and chat endpoint
requirements.txt   Python dependencies
data/              Source .txt and .pdf documents
db/                Persistent ChromaDB data
static/widget.html Browser chat widget
test_suite.py      API integration checks
```
