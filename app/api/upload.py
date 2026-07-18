import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import get_document_service
from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.models.user import User
from app.rag.loader import UnsupportedFileType
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

# Hard ceiling on upload size so a single request can't exhaust disk/memory.
# 25 MB is generous for the manuals/specs/reports this app targets.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    num_chunks: int


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
):
    # `file.filename` is fully client-controlled. Using it directly in a
    # filesystem path (the original code did `os.path.join(upload_dir,
    # file.filename)`) lets a filename like "../../app/main.py" or
    # "/etc/cron.d/x" escape the upload directory entirely -- a classic
    # path traversal / arbitrary file write. We keep the original name only
    # for display/citations and always write to disk under a name we
    # generate ourselves.
    original_filename = os.path.basename(file.filename or "")
    ext = os.path.splitext(original_filename)[1].lower()
    if not original_filename or ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    settings = get_settings()
    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_disk_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(settings.upload_dir, safe_disk_name)

    size = 0
    try:
        with open(dest_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit",
                    )
                buffer.write(chunk)
    except HTTPException:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise

    try:
        result = document_service.ingest(dest_path, original_filename, owner=current_user.username)
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        # The FAISS store keeps chunk text, not the original file, so the
        # on-disk copy under `safe_disk_name` was only needed for parsing.
        if os.path.exists(dest_path):
            os.remove(dest_path)

    logger.info("User '%s' uploaded '%s'", current_user.username, original_filename)
    return result
