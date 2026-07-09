"""
Thin wrapper around FAISS so the rest of the app never touches the FAISS
API directly. Also keeps a parallel list of metadata (doc_id, filename,
page number, chunk text) because FAISS itself only stores vectors +ids.

Persisted to disk as two files so a container restart doesn't lose the
index: `index.faiss` (vectors) and `metadata.json` (everything else).
"""

import json
import os
import threading

import faiss
import numpy as np

from app.core.config import get_settings


class VectorStore:
    def __init__(self, store_dir: str | None = None):
        settings = get_settings()
        self.store_dir = store_dir or settings.vector_store_dir
        self.dim = settings.embedding_dim
        self.index_path = os.path.join(self.store_dir, "index.faiss")
        self.metadata_path = os.path.join(self.store_dir, "metadata.json")
        self._lock = threading.Lock()

        os.makedirs(self.store_dir, exist_ok=True)
        self._load_or_create()

    def _load_or_create(self) -> None:
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                self.metadata: list[dict] = json.load(f)
        else:
            # Inner product on normalized vectors == cosine similarity.
            self.index = faiss.IndexFlatIP(self.dim)
            self.metadata = []

    def _persist(self) -> None:
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def add(self, vectors: np.ndarray, records: list[dict]) -> None:
        """records[i] must correspond to vectors[i], e.g.
        {"doc_id": ..., "filename": ..., "page_number": ..., "text": ...}
        """
        assert len(records) == vectors.shape[0], "vectors/records length mismatch"

        with self._lock:
            self.index.add(vectors)
            self.metadata.extend(records)
            self._persist()

    def search(self, query_vector: np.ndarray, top_k: int) -> list[dict]:
        if self.index.ntotal == 0:
            return []

        top_k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_vector.reshape(1, -1), top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            record = dict(self.metadata[idx])
            record["score"] = float(score)
            results.append(record)
        return results

    def delete_document(self, doc_id: str) -> int:
        """FAISS's FlatIP doesn't support in-place deletion by id well, so
        we rebuild the index without the deleted document's vectors. Fine
        for the data sizes this demo targets; a production deployment with
        millions of chunks would use IndexIDMap + remove_ids instead."""
        with self._lock:
            keep_indices = [i for i, m in enumerate(self.metadata) if m["doc_id"] != doc_id]
            removed = len(self.metadata) - len(keep_indices)
            if removed == 0:
                return 0

            if keep_indices:
                all_vectors = self.index.reconstruct_n(0, self.index.ntotal)
                kept_vectors = all_vectors[keep_indices]
                new_index = faiss.IndexFlatIP(self.dim)
                new_index.add(kept_vectors)
                self.index = new_index
                self.metadata = [self.metadata[i] for i in keep_indices]
            else:
                self.index = faiss.IndexFlatIP(self.dim)
                self.metadata = []

            self._persist()
            return removed

    def list_documents(self) -> list[dict]:
        seen = {}
        for m in self.metadata:
            doc_id = m["doc_id"]
            if doc_id not in seen:
                seen[doc_id] = {"doc_id": doc_id, "filename": m["filename"], "num_chunks": 0}
            seen[doc_id]["num_chunks"] += 1
        return list(seen.values())
