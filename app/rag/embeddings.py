"""
Two embedding backends behind one interface:

  - "hash": deterministic, pure numpy, zero network calls. Good enough to
    prove the whole pipeline works end-to-end and to run in CI/offline.
  - "sentence-transformers": real semantic embeddings, downloads model
    weights on first use, use this in production.

Swapping backends is a one-line config change (EMBEDDING_BACKEND in .env)
because everything downstream only ever calls `embed_texts(...)`.
"""

import hashlib
import logging

import numpy as np

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_st_model = None  # lazy-loaded singleton for the sentence-transformers backend


def embed_texts(texts: list[str]) -> np.ndarray:
    settings = get_settings()

    if settings.embedding_backend == "sentence-transformers":
        return _embed_with_sentence_transformers(texts)

    return _embed_with_hash(texts)


def _embed_with_hash(texts: list[str]) -> np.ndarray:
    """
    Deterministic bag-of-words style embedding: each word is hashed into
    one of `embedding_dim` buckets and we count occurrences, then
    L2-normalize. It won't understand synonyms, but identical/overlapping
    wording (which covers a surprising number of real support questions)
    retrieves correctly, and it never needs the network.
    """
    settings = get_settings()
    dim = settings.embedding_dim
    vectors = np.zeros((len(texts), dim), dtype="float32")

    for i, text in enumerate(texts):
        for word in text.lower().split():
            bucket = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16) % dim
            vectors[i, bucket] += 1.0

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # avoid divide-by-zero for empty strings
    return vectors / norms


def _embed_with_sentence_transformers(texts: list[str]) -> np.ndarray:
    global _st_model

    if _st_model is None:
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        logger.info("Loading sentence-transformers model: %s", settings.embedding_model_name)
        _st_model = SentenceTransformer(settings.embedding_model_name)

    embeddings = _st_model.encode(texts, normalize_embeddings=True)
    return np.asarray(embeddings, dtype="float32")
