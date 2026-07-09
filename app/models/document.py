"""
Metadata about an uploaded document. This is intentionally lightweight --
the actual searchable content lives as vectors in the FAISS store, this
class just tracks "what did we ingest and when".
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class DocumentMeta:
    doc_id: str
    filename: str
    num_chunks: int
    uploaded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
