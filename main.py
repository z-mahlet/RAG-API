import os
import re
from fastapi import FastAPI, HTTPException, UploadFile, File, Request, status
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import chromadb
from google import genai
from google.genai import types

# SlowAPI rate limiting imports
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from tenant_store import tenant_store, TenantConfig
from parsers import extract_text, chunk_text, DocumentParserError

# Initialize rate limiter using client IP address
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Multi-Tenant RAG Backend Platform",
    version="4.0.0",
    description="Production-hardened, multi-tenant RAG platform with rate limiting and vector isolation."
)

# Register SlowAPI exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse("static/widget.html")


@app.get("/demo", include_in_schema=False)
def demo():
    return FileResponse("static/test_host.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=status.HTTP_204_NO_CONTENT)


gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)


def get_tenant_collection_name(tenant_id: str) -> str:
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "_", tenant_id).strip("_")
    if not clean_id:
        clean_id = "default"
    col_name = f"tenant_{clean_id}"
    return col_name[:63]


def get_tenant_collection(tenant_id: str):
    col_name = get_tenant_collection_name(tenant_id)
    return chroma_client.get_or_create_collection(
        name=col_name,
        metadata={"hnsw:space": "cosine"}
    )


# --- Request & Response Models ---

class TenantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User question")
    top_k: int = Field(default=3, ge=1, le=10, description="Context passages to retrieve")


class SourceDocument(BaseModel):
    content: str
    metadata: dict
    distance: float


class TenantChatResponse(BaseModel):
    reply: str
    sources: list[SourceDocument]
    fallback_triggered: bool


class UploadResponse(BaseModel):
    filename: str
    chunks_indexed: int
    total_tenant_chunks: int
    status: str


# --- Health & Config Endpoints ---

@app.get("/health", status_code=status.HTTP_200_OK)
def health():
    return {"status": "healthy"}


@app.get("/api/v1/tenant/{tenant_id}/config", response_model=TenantConfig)
def get_tenant_configuration(tenant_id: str):
    return tenant_store.get(tenant_id)


@app.put("/api/v1/tenant/{tenant_id}/config", response_model=TenantConfig)
def update_tenant_configuration(tenant_id: str, config_update: TenantConfig):
    config_update.tenant_id = tenant_id
    return tenant_store.save(config_update)


# --- Hardened Ingestion & Management ---

@app.post("/api/v1/tenant/{tenant_id}/upload", response_model=UploadResponse)
@limiter.limit("5/minute")  # Prevent free-tier quota exhaustion from rapid file uploads
async def upload_document(request: Request, tenant_id: str, file: UploadFile = File(...)):
    file_bytes = await file.read()
    max_size = 10 * 1024 * 1024  # 10MB memory safety ceiling
    if len(file_bytes) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds the 10 MB limit."
        )

    try:
        raw_text = extract_text(file.filename, file_bytes)
    except DocumentParserError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not raw_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document appears to be empty or contains no extractable text."
        )

    chunks = chunk_text(raw_text, chunk_size=80, overlap=20)
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not generate chunks from the provided document."
        )

    try:
        emb_res = gemini_client.models.embed_content(
            model=settings.EMBEDDING_MODEL,
            contents=chunks
        )
        embeddings = [item.values for item in emb_res.embeddings]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gemini embedding error: {str(e)}"
        )

    collection = get_tenant_collection(tenant_id)
    doc_ids = [f"{file.filename}_chunk_{idx}" for idx in range(len(chunks))]
    metadatas = [
        {"source": file.filename, "chunk_index": idx, "tenant_id": tenant_id}
        for idx in range(len(chunks))
    ]

    collection.upsert(
        ids=doc_ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas
    )

    return UploadResponse(
        filename=file.filename,
        chunks_indexed=len(chunks),
        total_tenant_chunks=collection.count(),
        status="success"
    )


@app.get("/api/v1/tenant/{tenant_id}/documents")
def list_tenant_documents(tenant_id: str):
    collection = get_tenant_collection(tenant_id)
    total_records = collection.count()

    if total_records == 0:
        return {"tenant_id": tenant_id, "total_chunks": 0, "sources": []}

    data = collection.get(include=["metadatas"])
    sources = set(m.get("source", "unknown") for m in data.get("metadatas", []))

    return {
        "tenant_id": tenant_id,
        "total_chunks": total_records,
        "sources": sorted(list(sources))
    }


@app.delete("/api/v1/tenant/{tenant_id}/documents")
def clear_tenant_documents(tenant_id: str):
    col_name = get_tenant_collection_name(tenant_id)
    try:
        chroma_client.delete_collection(name=col_name)
        return {"status": "cleared", "tenant_id": tenant_id, "message": "All tenant documents wiped."}
    except Exception:
        return {"status": "cleared", "tenant_id": tenant_id, "message": "Collection was already empty."}


# --- Hardened Grounded Chat Endpoint ---

@app.post("/api/v1/tenant/{tenant_id}/chat", response_model=TenantChatResponse)
@limiter.limit("20/minute")
async def tenant_chat(request: Request, tenant_id: str, payload: TenantChatRequest):
    tenant = tenant_store.get(tenant_id)
    collection = get_tenant_collection(tenant_id)
    total_docs = collection.count()

    # =========================================================================
    # SCENARIO A: NO DOCUMENTS UPLOADED YET
    # =========================================================================
    if total_docs == 0:
        # If tenant disallows general chat, strictly return fallback
        if not tenant.allow_general_chat:
            return TenantChatResponse(
                reply=tenant.fallback_message,
                sources=[],
                fallback_triggered=True
            )

        # Otherwise, engage in general conversation and explain the host app
        general_system_prompt = (
            f"Persona & Tone Instructions:\n{tenant.system_persona}\n\n"
            f"About the Host Application:\n{tenant.app_description}\n\n"
            "Guidelines:\n"
            "1. You are embedded inside the host application described above.\n"
            "2. If the user asks what this website, app, or tool does, explain it using the 'About the Host Application' information.\n"
            "3. Help the user conversationally and answer general questions politely and concisely.\n"
            "4. Do not mention that documents are missing or that you lack a knowledge base."
        )

        try:
            response = gemini_client.models.generate_content(
                model=settings.LLM_MODEL,
                contents=payload.message,
                config=types.GenerateContentConfig(
                    system_instruction=general_system_prompt,
                    temperature=0.7,  # Moderate temperature for natural conversation
                )
            )
            return TenantChatResponse(
                reply=response.text or tenant.greeting_message,
                sources=[],
                fallback_triggered=False
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"General chat error: {str(e)}"
            )

    # =========================================================================
    # SCENARIO B: DOCUMENTS ARE UPLOADED (RAG PIPELINE)
    # =========================================================================
    try:
        # 1. Embed query
        emb_res = gemini_client.models.embed_content(
            model=settings.EMBEDDING_MODEL,
            contents=payload.message
        )
        query_vector = emb_res.embeddings[0].values

        # 2. Query tenant collection
        search_results = collection.query(
            query_embeddings=[query_vector],
            n_results=payload.top_k
        )

        documents = search_results.get("documents", [[]])[0]
        metadatas = search_results.get("metadatas", [[]])[0]
        distances = search_results.get("distances", [[]])[0]

        sources: list[SourceDocument] = []
        valid_context_blocks = []

        for doc, meta, dist in zip(documents, metadatas, distances):
            sources.append(SourceDocument(content=doc, metadata=meta, distance=round(dist, 4)))
            if dist <= tenant.max_distance_threshold:
                source_name = meta.get("source", "doc")
                valid_context_blocks.append(f"[{source_name}]: {doc}")

        # If documents were searched but no relevant matches passed the threshold
        if not valid_context_blocks:
            if not tenant.allow_general_chat:
                return TenantChatResponse(
                    reply=tenant.fallback_message,
                    sources=sources,
                    fallback_triggered=True
                )
            
            # Hybrid fallback: answer using app description & general intelligence
            hybrid_prompt = (
                f"Persona:\n{tenant.system_persona}\n\n"
                f"Host Application Info:\n{tenant.app_description}\n\n"
                "Note: Specific knowledge documents had no close match for this query. "
                "Answer using the host application description or general assistance. "
                "If it requires proprietary data you don't know, state: "
                f"'{tenant.fallback_message}'"
            )
            response = gemini_client.models.generate_content(
                model=settings.LLM_MODEL,
                contents=payload.message,
                config=types.GenerateContentConfig(
                    system_instruction=hybrid_prompt,
                    temperature=0.5,
                )
            )
            return TenantChatResponse(
                reply=response.text or tenant.fallback_message,
                sources=sources,
                fallback_triggered=False
            )

        # Grounded RAG generation with context
        context_str = "\n\n".join(valid_context_blocks)
        system_instruction = (
            f"Persona & Tone Instructions:\n{tenant.system_persona}\n\n"
            f"Host Application Overview:\n{tenant.app_description}\n\n"
            "Grounding Rules:\n"
            "1. Answer the query relying primarily on the Context below.\n"
            f"2. If the context does not answer the question, output: '{tenant.fallback_message}'\n\n"
            f"Context:\n{context_str}"
        )

        response = gemini_client.models.generate_content(
            model=settings.LLM_MODEL,
            contents=payload.message,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
            )
        )

        reply_text = response.text if response.text else tenant.fallback_message
        fallback_used = tenant.fallback_message.strip() in reply_text.strip()

        return TenantChatResponse(
            reply=reply_text,
            sources=sources,
            fallback_triggered=fallback_used
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat error for tenant '{tenant_id}': {str(e)}"
        )

@app.post("/api/chat")
@limiter.limit("20/minute")
async def legacy_chat(request: Request, payload: dict):
    tenant_id = payload.get("tenant_id", "default")
    req = TenantChatRequest(message=payload["message"], top_k=payload.get("top_k", 3))
    return await tenant_chat(request, tenant_id, req)