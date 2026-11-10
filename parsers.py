import io
import csv
from pypdf import PdfReader
from docx import Document


class DocumentParserError(Exception):
    """Custom exception raised when file parsing fails."""
    pass


def extract_text(filename: str, file_bytes: bytes) -> str:
    """
    Detects file extension and routes bytes to the corresponding extractor.
    Supported: .pdf, .docx, .txt, .md, .csv
    """
    ext = filename.lower().split(".")[-1]
    stream = io.BytesIO(file_bytes)

    if ext == "pdf":
        return _parse_pdf(stream)
    elif ext == "docx":
        return _parse_docx(stream)
    elif ext in ["txt", "md"]:
        return _parse_plaintext(file_bytes)
    elif ext == "csv":
        return _parse_csv(file_bytes)
    else:
        raise DocumentParserError(f"Unsupported file format: .{ext}")


def _parse_pdf(stream: io.BytesIO) -> str:
    try:
        reader = PdfReader(stream)
        pages_text = []
        for idx, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages_text.append(f"--- Page {idx + 1} ---\n{text}")
        return "\n\n".join(pages_text).strip()
    except Exception as e:
        raise DocumentParserError(f"Failed to parse PDF document: {str(e)}")


def _parse_docx(stream: io.BytesIO) -> str:
    try:
        doc = Document(stream)
        parts = []
        # Extract paragraphs
        for p in doc.paragraphs:
            if p.text.strip():
                parts.append(p.text.strip())
        # Extract tables
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    parts.append(row_text)
        return "\n".join(parts).strip()
    except Exception as e:
        raise DocumentParserError(f"Failed to parse DOCX document: {str(e)}")


def _parse_plaintext(file_bytes: bytes) -> str:
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1", errors="replace")


def _parse_csv(file_bytes: bytes) -> str:
    try:
        content = _parse_plaintext(file_bytes)
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        if not rows:
            return ""

        headers = [h.strip() for h in rows[0]]
        serialized_rows = []

        for row_idx, row in enumerate(rows[1:], start=1):
            if not any(row):
                continue
            row_items = []
            for col_idx, cell in enumerate(row):
                header_name = headers[col_idx] if col_idx < len(headers) else f"Col_{col_idx + 1}"
                row_items.append(f"{header_name}: {cell.strip()}")
            serialized_rows.append(f"[Record {row_idx}] " + " | ".join(row_items))

        return "\n".join(serialized_rows)
    except Exception as e:
        raise DocumentParserError(f"Failed to parse CSV document: {str(e)}")


def chunk_text(text: str, chunk_size: int = 80, overlap: int = 20) -> list[str]:
    """Sliding-window word-level chunking."""
    words = text.split()
    if not words:
        return []
    chunks = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        chunks.append(" ".join(words[i:i + chunk_size]))
        if i + chunk_size >= len(words):
            break
    return chunks