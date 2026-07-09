"""
Shared dependencies for the API layer. `VectorStore` is expensive-ish to
load (reads the FAISS index off disk), so we keep one instance per
process instead of re-loading it on every request.
"""

from functools import lru_cache

from app.rag.vector_store import VectorStore
from app.services.document_service import DocumentService


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()


@lru_cache
def get_document_service() -> DocumentService:
    return DocumentService(vector_store=get_vector_store())
