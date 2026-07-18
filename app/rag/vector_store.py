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

    def search(self, query_vector: np.ndarray, top_k: int, owner: str | None = None) -> list[dict]:
        if self.index.ntotal == 0:
            return []

        # When scoping to one owner we can't just ask FAISS for top_k and
        # filter afterwards -- if another user's chunks rank higher we'd
        # come back with fewer than top_k (or zero) results even though
        # the owner has plenty of matching content. So when `owner` is
        # set we pull every match and filter+truncate ourselves. FlatIP is
        # a brute-force index anyway, so this costs nothing extra at the
        # data sizes this app targets.
        search_k = self.index.ntotal if owner is not None else min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_vector.reshape(1, -1), search_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            record = dict(self.metadata[idx])
            if owner is not None and record.get("owner") != owner:
                continue
            record["score"] = float(score)
            results.append(record)
            if len(results) >= top_k:
                break
        return results

    def delete_document(self, doc_id: str, owner: str | None = None) -> int:
        """FAISS's FlatIP doesn't support in-place deletion by id well, so
        we rebuild the index without the deleted document's vectors. Fine
        for the data sizes this demo targets; a production deployment with
        millions of chunks would use IndexIDMap + remove_ids instead.

        When `owner` is given, only chunks matching both doc_id AND owner
        are removed -- deleting someone else's doc_id is a no-op (reported
        as 0 removed, same as "not found", so we don't leak whether the id
        exists for another user)."""
        with self._lock:
            keep_indices = [
                i
                for i, m in enumerate(self.metadata)
                if not (m["doc_id"] == doc_id and (owner is None or m.get("owner") == owner))
            ]
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

    def get_chunks(self, doc_id: str, owner: str | None = None) -> list[dict]:
        """Return every stored chunk for one document, optionally scoped to
        `owner`. Added so callers (DocumentService) never need to reach
        into `self.metadata` directly -- every other read path here
        (search, list_documents, delete_document) is already a method on
        this class; get_full_text() in DocumentService was the one
        exception, poking at a "private" list from outside the class that
        owns it.
        """
        return [
            dict(m)
            for m in self.metadata
            if m["doc_id"] == doc_id and (owner is None or m.get("owner") == owner)
        ]

    def list_documents(self, owner: str | None = None) -> list[dict]:
        seen = {}
        for m in self.metadata:
            if owner is not None and m.get("owner") != owner:
                continue
            doc_id = m["doc_id"]
            if doc_id not in seen:
                seen[doc_id] = {"doc_id": doc_id, "filename": m["filename"], "num_chunks": 0}
            seen[doc_id]["num_chunks"] += 1
        return list(seen.values())
