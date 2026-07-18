import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_document_service
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.analysis_service import extract_requirements, summarize_document
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


# Response schemas.
#
# Before this pass, every handler in this file returned a bare dict, while
# app/api/chat.py already used a `response_model`. That split meant these
# endpoints had no schema in the OpenAPI docs, no field-type guarantees,
# and no protection if a service layer change accidentally reshaped what
# got returned. Every route in the app now declares a `response_model`, so
# the contract is uniform: chat, search, upload, and documents all document
# and enforce their response shape the same way.
class DocumentSummary(BaseModel):
    doc_id: str
    filename: str
    num_chunks: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary]


class DeleteResponse(BaseModel):
    message: str


class SummaryResponse(BaseModel):
    doc_id: str
    summary: str


class RequirementsResponse(BaseModel):
    doc_id: str
    requirements: list[str]


@router.get("", response_model=DocumentListResponse)
def list_documents(
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
):
    return DocumentListResponse(documents=document_service.list_documents(owner=current_user.username))


@router.delete("/{doc_id}", response_model=DeleteResponse)
def delete_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
):
    removed = document_service.delete(doc_id, owner=current_user.username)
    if removed == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    logger.info("User '%s' deleted document %s (%d chunks removed)", current_user.username, doc_id, removed)
    return DeleteResponse(message=f"Deleted {removed} chunks for document {doc_id}")


@router.get("/{doc_id}/summary", response_model=SummaryResponse)
def get_summary(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
):
    try:
        full_text = document_service.get_full_text(doc_id, owner=current_user.username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return SummaryResponse(doc_id=doc_id, summary=summarize_document(full_text))


@router.get("/{doc_id}/requirements", response_model=RequirementsResponse)
def get_requirements(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
):
    try:
        full_text = document_service.get_full_text(doc_id, owner=current_user.username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return RequirementsResponse(doc_id=doc_id, requirements=extract_requirements(full_text))
