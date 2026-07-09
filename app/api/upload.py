import logging
import os
import shutil

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.api.deps import get_document_service
from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.models.user import User
from app.rag.loader import UnsupportedFileType
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


@router.post("/upload")
async def upload_document(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    settings = get_settings()
    os.makedirs(settings.upload_dir, exist_ok=True)
    dest_path = os.path.join(settings.upload_dir, file.filename)

    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        result = document_service.ingest(dest_path, file.filename)
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    logger.info("User '%s' uploaded '%s'", current_user.username, file.filename)
    return result
