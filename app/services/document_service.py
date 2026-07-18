"""
Orchestrates the full ingestion pipeline:

    file on disk -> load -> chunk -> embed -> store in FAISS

This is the class the /upload endpoint actually talks to, so the router
stays thin (HTTP concerns only) and this stays testable without HTTP.
"""

import logging
import uuid

from app.rag.chunker import chunk_pages
from app.rag.embeddings import embed_texts
from app.rag.loader import load_document
from app.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, vector_store: VectorStore | None = None):
        self.vector_store = vector_store or VectorStore()

    def ingest(self, file_path: str, filename: str, owner: str) -> dict:
        doc_id = str(uuid.uuid4())

        pages = load_document(file_path)
        if not pages:
            raise ValueError(f"No extractable text found in '{filename}'")

        chunks = chunk_pages(pages)
        if not chunks:
            raise ValueError(f"Document '{filename}' produced no chunks")

        vectors = embed_texts([c.text for c in chunks])
        records = [
            {
                "doc_id": doc_id,
                "filename": filename,
                "page_number": c.page_number,
                "text": c.text,
                "owner": owner,
            }
            for c in chunks
        ]

        self.vector_store.add(vectors, records)
        logger.info("Ingested '%s' as doc_id=%s (%d chunks) for '%s'", filename, doc_id, len(chunks), owner)

        return {"doc_id": doc_id, "filename": filename, "num_chunks": len(chunks)}

    def get_full_text(self, doc_id: str, owner: str) -> str:
        """Reassemble a document's text from its stored chunks -- used by
        the summarization / requirements-extraction endpoints so they
        don't need to re-read the original file from disk.

        Scoped to `owner` so one user can't pull another user's document
        text by guessing/enumerating doc ids."""
        chunks = [
            m for m in self.vector_store.metadata if m["doc_id"] == doc_id and m.get("owner") == owner
        ]
        if not chunks:
            raise ValueError(f"No document found with id '{doc_id}'")
        return "\n".join(c["text"] for c in chunks)

    def list_documents(self, owner: str) -> list[dict]:
        return self.vector_store.list_documents(owner=owner)

    def delete(self, doc_id: str, owner: str) -> int:
        return self.vector_store.delete_document(doc_id, owner=owner)
