import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_document_service
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.analysis_service import extract_requirements, summarize_document
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("")
def list_documents(
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
):
    return {"documents": document_service.list_documents()}


@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
):
    removed = document_service.delete(doc_id)
    if removed == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    logger.info("User '%s' deleted document %s (%d chunks removed)", current_user.username, doc_id, removed)
    return {"message": f"Deleted {removed} chunks for document {doc_id}"}


@router.get("/{doc_id}/summary")
def get_summary(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
):
    try:
        full_text = document_service.get_full_text(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {"doc_id": doc_id, "summary": summarize_document(full_text)}


@router.get("/{doc_id}/requirements")
def get_requirements(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
):
    try:
        full_text = document_service.get_full_text(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {"doc_id": doc_id, "requirements": extract_requirements(full_text)}
