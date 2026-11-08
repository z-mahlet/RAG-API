import os
import glob
from pypdf import PdfReader
import chromadb
from google import genai
from config import settings


def get_gemini_client() -> genai.Client:
    """Instantiate and return the Gemini client with validated settings."""
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def get_vector_collection(chroma_client: chromadb.PersistentClient):
    """Retrieve or create the ChromaDB collection configured for cosine distance."""
    return chroma_client.get_or_create_collection(
        name=settings.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )


def extract_text_from_file(file_path: str) -> str:
    """Reads raw text from supported file formats (.txt and .pdf)."""
    text_content = ""
    if file_path.endswith(".txt"):
        with open(file_path, "r", encoding="utf-8") as f:
            text_content = f.read()
    elif file_path.endswith(".pdf"):
        reader = PdfReader(file_path)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text_content += extracted + "\n"
    return text_content.strip()


def chunk_text(text: str, chunk_size: int = 60, overlap: int = 15) -> list[str]:
    """
    Splits text into overlapping chunks based on word count.
    
    Args:
        text: Raw source text.
        chunk_size: Maximum number of words per chunk.
        overlap: Number of overlapping words between consecutive chunks.
    """
    words = text.split()
    if not words:
        return []
    
    chunks = []
    step = max(1, chunk_size - overlap)
    
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        # Terminate when the current window reaches or surpasses the end
        if i + chunk_size >= len(words):
            break
            
    return chunks


def process_documents(data_dir: str = "./data"):
    """Scans the data directory, extracts text, generates embeddings, and saves to ChromaDB."""
    gemini_client = get_gemini_client()
    chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    collection = get_vector_collection(chroma_client)

    search_pattern = os.path.join(data_dir, "*")
    files = [f for f in glob.glob(search_pattern) if f.endswith((".txt", ".pdf"))]

    if not files:
        print(f"[!] No supported files (.txt, .pdf) found in '{data_dir}'.")
        return

    print(f"[*] Found {len(files)} document(s) in '{data_dir}' to process.")

    all_chunks: list[str] = []
    all_metadatas: list[dict] = []
    all_ids: list[str] = []

    for file_path in files:
        filename = os.path.basename(file_path)
        content = extract_text_from_file(file_path)
        
        if not content:
            print(f"[-] Skipping empty or unreadable file: {filename}")
            continue

        chunks = chunk_text(content, chunk_size=60, overlap=15)
        print(f"[+] '{filename}' partitioned into {len(chunks)} chunks.")

        for idx, chunk in enumerate(chunks):
            chunk_id = f"{filename}_chunk_{idx}"
            all_chunks.append(chunk)
            all_metadatas.append({
                "source": filename,
                "chunk_index": idx
            })
            all_ids.append(chunk_id)

    if not all_chunks:
        print("[!] No text could be extracted from the target files.")
        return

    print(f"[*] Requesting embeddings from Gemini model '{settings.EMBEDDING_MODEL}' for {len(all_chunks)} chunks...")
    
    # Batch embeddings request
    embedding_response = gemini_client.models.embed_content(
        model=settings.EMBEDDING_MODEL,
        contents=all_chunks
    )
    embeddings = [record.values for record in embedding_response.embeddings]
    
    print(f"[*] Upserting {len(all_chunks)} vectors into ChromaDB collection '{settings.COLLECTION_NAME}'...")
    collection.upsert(
        ids=all_ids,
        documents=all_chunks,
        embeddings=embeddings,
        metadatas=all_metadatas
    )

    print(f"[✓] Document ingestion complete. Collection now holds {collection.count()} item(s).")


if __name__ == "__main__":
    process_documents()