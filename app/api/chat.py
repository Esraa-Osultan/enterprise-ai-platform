import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_vector_store
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.rag.pipeline import build_chat_response
from app.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int | None = None


class ChatSource(BaseModel):
    filename: str
    page: int
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    vector_store: VectorStore = Depends(get_vector_store),
):
    logger.info("User '%s' asked: %s", current_user.username, payload.question)
    return build_chat_response(payload.question, vector_store, payload.top_k)
