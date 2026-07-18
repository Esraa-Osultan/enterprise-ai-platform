from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_vector_store
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.rag.pipeline import retrieve
from app.rag.vector_store import VectorStore

router = APIRouter(tags=["Search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = None


class SearchResult(BaseModel):
    filename: str
    page: int
    text: str
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]


@router.post("/search", response_model=SearchResponse)
def search(
    payload: SearchRequest,
    current_user: User = Depends(get_current_user),
    vector_store: VectorStore = Depends(get_vector_store),
):
    results = retrieve(payload.query, vector_store, payload.top_k, owner=current_user.username)
    return SearchResponse(
        results=[
            SearchResult(
                filename=r["filename"],
                page=r["page_number"],
                text=r["text"],
                score=round(r["score"], 4),
            )
            for r in results
        ]
    )
