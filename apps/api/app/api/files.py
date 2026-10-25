import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models import DocumentEvent, StudentDocument, User
from app.services.agent_documents import STORAGE_PREFIX
from app.services.storage import storage

router = APIRouter(prefix="/files", tags=["files"])


def _allowed(content_type: str) -> bool:
    return content_type in {item.strip() for item in settings.allowed_upload_types.split(",") if item.strip()}


@router.post("/presign")
async def presign(payload: dict, user: User = Depends(get_current_user)):
    content_type = str(payload.get("content_type") or "application/octet-stream")
    size = int(payload.get("size") or 0)
    if not _allowed(content_type):
        raise HTTPException(415, "This file type is not allowed")
    if size < 1 or size > settings.max_upload_bytes:
        raise HTTPException(413, f"File size must be between 1 and {settings.max_upload_bytes} bytes")
    return storage.presign_upload(str(payload.get("filename") or "upload.bin"), content_type)


@router.post("/local-upload")
async def local_upload(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    if settings.aws_s3_bucket:
        raise HTTPException(400, "Use presigned S3 upload")
    if not _allowed(file.content_type or "application/octet-stream"):
        raise HTTPException(415, "This file type is not allowed")
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "File too large")
    filename = Path(file.filename or "upload.bin").name.replace(" ", "-")[:180]
    dest = Path(settings.local_upload_dir) / "uploads" / f"{user.id}-{uuid.uuid4().hex}-{filename}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"url": f"/local-files/uploads/{dest.name}", "size": len(data), "content_type": file.content_type}


async def _overseas_document(db: AsyncSession, key: str) -> bool:
    """ccrm-022 SD5: the key is (or was) an overseas student document's file -- in either stored shape, current, archived or replaced."""
    if key.startswith(f"{STORAGE_PREFIX}/"):
        return True
    shapes = (key, f"/{key}", f"/local-files/{key}")
    if await db.scalar(select(StudentDocument.id).where(StudentDocument.file_url.in_(shapes)).limit(1)):
        return True
    return bool(await db.scalar(select(DocumentEvent.id).where(DocumentEvent.file_key.in_(shapes)).limit(1)))


@router.get("/download")
async def download(key: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if ".." in key or key.startswith(("/", "\\")):
        raise HTTPException(422, "Invalid object key")
    if key.startswith("agent-kyc/"):  # AGN-024: KYC files are served only by the admin streaming route
        raise HTTPException(404, "Not found")
    if await _overseas_document(db, key):  # ccrm-022 SD5: only the scope-checked, audited document download hands these out
        raise HTTPException(404, "Not found")
    return {"url": storage.presign_download(key), "expires_in": 900 if settings.aws_s3_bucket else None}
