from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import chromadb
from google import genai
from google.genai import types
from config import settings

# 1. Initialize FastAPI Application
app = FastAPI(
    title="Universal RAG Backend API",
    version="1.0.0",
    description="Reusable RAG backend with semantic vector search and Google Gemini synthesis."
)

# 2. Configure Cross-Origin Resource Sharing (CORS)
# Allows portable web widgets and external client apps to communicate with this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to specific trusted domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Instantiate Persistent Clients
gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
collection = chroma_client.get_or_create_collection(
    name=settings.COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}
)


# 4. Define Request and Response Schemas
class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        description="The user's question or search prompt."
    )
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of relevant document chunks to retrieve."
    )


class SourceDocument(BaseModel):
    content: str
    metadata: dict


class ChatResponse(BaseModel):
    reply: str
    sources: list[SourceDocument]


# 5. Health Check Endpoint
@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Liveness probe verifying that the API is running and the collection is accessible."""
    return {
        "status": "healthy",
        "collection": settings.COLLECTION_NAME,
        "indexed_records": collection.count()
    }


# 6. Core Chat Endpoint
@app.post("/api/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_endpoint(payload: ChatRequest):
    try:
        # Step A: Convert the user's incoming question into a vector embedding
        embedding_res = gemini_client.models.embed_content(
            model=settings.EMBEDDING_MODEL,
            contents=payload.message
        )
        query_vector = embedding_res.embeddings[0].values

        # Step B: Perform semantic vector search in ChromaDB
        search_results = collection.query(
            query_embeddings=[query_vector],
            n_results=payload.top_k
        )

        documents = search_results.get("documents", [[]])[0]
        metadatas = search_results.get("metadatas", [[]])[0]

        # Step C: Format retrieved documents into context blocks and extract sources
        context_blocks = []
        sources = []
        for doc, meta in zip(documents, metadatas):
            source_file = meta.get("source", "unknown")
            chunk_idx = meta.get("chunk_index", "0")
            context_blocks.append(f"--- Document [{source_file} | Chunk {chunk_idx}] ---\n{doc}")
            sources.append(SourceDocument(content=doc, metadata=meta))

        context_text = "\n\n".join(context_blocks) if context_blocks else "No relevant context found."

        # Step D: Construct prompt with strict grounding rules
        system_instruction = (
            "You are a professional, helpful AI knowledge assistant. Answer the user's query "
            "truthfully and concisely relying exclusively on the provided Context below.\n"
            "Rules:\n"
            "1. If the answer cannot be determined directly from the Context, state clearly: "
            "'I do not have sufficient information in the knowledge base to answer this question.'\n"
            "2. Do not invent facts, speculate, or draw from outside knowledge not present in the Context.\n\n"
            f"Context:\n{context_text}"
        )

        # Step E: Generate grounded answer via Gemini
        response = gemini_client.models.generate_content(
            model=settings.LLM_MODEL,
            contents=payload.message,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,  # Low temperature for factual precision
            )
        )

        reply_content = response.text if response.text else "No response generated."

        return ChatResponse(
            reply=reply_content,
            sources=sources
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing RAG query: {str(e)}"
        )