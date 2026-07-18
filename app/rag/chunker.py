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


def _extend_to_word_boundary(text: str, end: int) -> int:
    """Nudge `end` forward to the next whitespace so we don't cut a word in
    half. Without this, a boundary landing inside a word (e.g. "calibra|
    tion") splits it into two garbage tokens for the hash embedding
    backend, which tokenizes on whitespace -- neither half then matches a
    real query term. Bounded to a small lookahead so one long unbroken
    token (e.g. a URL) can't blow the chunk size out arbitrarily.
    """
    limit = min(len(text), end + 40)
    while end < limit and not text[end].isspace():
        end += 1
    return end


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
            if end < len(text):
                end = _extend_to_word_boundary(text, end)
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
