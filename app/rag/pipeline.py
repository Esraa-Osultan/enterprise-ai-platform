"""
The actual "ask a question, get an answer with sources" logic.

Retrieval always works (FAISS + our embeddings). Generation prefers a
real LLM call if an API key is configured; otherwise it falls back to an
extractive answer built from the retrieved chunks, so `POST /chat` never
just breaks because a key is missing -- it degrades gracefully instead.
"""

import logging

from app.core.config import get_settings
from app.rag.embeddings import embed_texts
from app.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)


def retrieve(
    query: str, vector_store: VectorStore, top_k: int | None = None, owner: str | None = None
) -> list[dict]:
    settings = get_settings()
    top_k = top_k or settings.top_k

    query_vector = embed_texts([query])[0]
    return vector_store.search(query_vector, top_k, owner=owner)


def generate_answer(query: str, sources: list[dict]) -> str:
    if not sources:
        return "No relevant information was found in the uploaded documents."

    settings = get_settings()
    if settings.openai_api_key:
        try:
            return _generate_with_llm(query, sources)
        except Exception as exc:  # noqa: BLE001 -- we want to fall back on ANY failure
            logger.warning("LLM call failed (%s), falling back to extractive answer", exc)

    return _generate_extractive(sources)


def _generate_with_llm(query: str, sources: list[dict]) -> str:
    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    context = "\n\n".join(
        f"[{s['filename']} - page {s['page_number']}]\n{s['text']}" for s in sources
    )
    prompt = (
        "Answer the question using ONLY the context below. "
        "If the answer isn't in the context, say so.\n\n"
        f"Context:\n{context}\n\nQuestion: {query}"
    )

    response = client.chat.completions.create(
        model=settings.llm_model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def _generate_extractive(sources: list[dict]) -> str:
    """No LLM available: return the single most relevant chunk verbatim
    as the answer, which is honest about what the system actually knows
    rather than pretending to reason over it."""
    best = sources[0]
    return best["text"]


def build_chat_response(
    query: str, vector_store: VectorStore, top_k: int | None = None, owner: str | None = None
) -> dict:
    sources = retrieve(query, vector_store, top_k, owner=owner)
    answer = generate_answer(query, sources)

    return {
        "answer": answer,
        "sources": [
            {
                "filename": s["filename"],
                "page": s["page_number"],
                "score": round(s["score"], 4),
            }
            for s in sources
        ],
    }
