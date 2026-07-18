"""
Splits page text into overlapping chunks. Overlap matters: without it,
a sentence that straddles a chunk boundary loses its meaning in both
halves, and the retriever ends up missing answers that were technically
"in" the document.
"""

from dataclasses import dataclass

from app.core.config import get_settings
from app.rag.loader import PageText


@dataclass
class Chunk:
    text: str
    page_number: int
    chunk_index: int


def chunk_pages(pages: list[PageText]) -> list[Chunk]:
    settings = get_settings()
    size = settings.chunk_size
    overlap = settings.chunk_overlap

    chunks: list[Chunk] = []
    running_index = 0

    for page in pages:
        text = page.text
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            piece = text[start:end].strip()
            if piece:
                chunks.append(
                    Chunk(text=piece, page_number=page.page_number, chunk_index=running_index)
                )
                running_index += 1
            if end == len(text):
                break
            start = end - overlap  # step forward, keeping the overlap

    return chunks
