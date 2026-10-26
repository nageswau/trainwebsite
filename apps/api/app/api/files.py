import hashlib
import mimetypes
import uuid
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import DocumentEvent, StoredFile, StudentDocument, User
from app.services import upload_policy
from app.services.agent_documents import STORAGE_PREFIX
from app.services.storage import storage

router = APIRouter(prefix="/files", tags=["files"])
# nehn-003 PS3: replaces the public `/local-files` StaticFiles mount; included without the /api/v1 prefix.
local_router = APIRouter(tags=["files"])
logger = get_logger("app.files")

PUBLIC_PREFIXES = ("public/",)
NOSNIFF = {"X-Content-Type-Options": "nosniff"}
INLINE_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp", "text/plain"}  # inert under nosniff


def _allowed(content_type: str) -> bool:
    return content_type in {item.strip() for item in settings.allowed_upload_types.split(",") if item.strip()}


def _checked(purpose: str, file: UploadFile) -> tuple[int, str]:
    """The upload's size and its (policy-allowed, so never empty) content type, or the policy's refusal."""
    try:
        return upload_policy.check_upload(purpose, file), str(file.content_type)
    except upload_policy.PolicyError as refused:
        raise HTTPException(refused.status_code, refused.detail) from None


def _safe_name(filename: str | None) -> str:
    return Path(filename or "upload.bin").name.replace(" ", "-")[:180] or "upload.bin"


def _sha256(stream) -> str:
    digest = hashlib.sha256()
    stream.seek(0)
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()


def _local_response(key: str, *, filename: str | None = None, media_type: str | None = None) -> FileResponse:
    path = storage.local_file(key)
    if path is None:
        raise HTTPException(404, "Not found")
    media_type = media_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if filename or media_type not in INLINE_TYPES:  # anything that could run in our origin (HTML, SVG…) is only ever a download
        return FileResponse(path, media_type=media_type, filename=filename or path.name, content_disposition_type="attachment", headers=NOSNIFF)
    return FileResponse(path, media_type=media_type, headers=NOSNIFF)


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
    size, content_type = _checked("default", file)  # nehn-003 PS6: today's types and limit, now sniffed and streamed through StorageService
    name = f"{user.id}-{uuid.uuid4().hex}-{_safe_name(file.filename)}"
    storage.write_stream(f"uploads/{name}", file.file, content_type)
    return {"url": f"/local-files/uploads/{name}", "size": size, "content_type": content_type}


@router.post("/upload", status_code=201)
async def upload(purpose: str = Query(..., max_length=40), file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """nehn-003 PS5: a policy-checked upload recorded in `stored_files`; the caller gets an id and the authorised download route."""
    size, content_type = _checked(purpose, file)
    key = f"files/{purpose}/{uuid.uuid4().hex}"
    row = StoredFile(key=key, purpose=purpose, owner_id=user.id, original_filename=(file.filename or "upload.bin")[:255], content_type=content_type, size_bytes=size, sha256=_sha256(file.file))
    storage.write_stream(key, file.file, content_type)
    db.add(row)
    try:
        await db.commit()
    except Exception:
        storage.delete(key)  # no orphan object when the row cannot be saved
        raise
    logger.info("file_stored", extra={"extra_fields": {"file_id": str(row.id), "purpose": purpose, "size": size}})
    return {"id": str(row.id), "purpose": purpose, "filename": row.original_filename, "content_type": row.content_type, "size": size, "url": f"/api/v1/files/{row.id}"}


async def _overseas_document(db: AsyncSession, key: str) -> bool:
    """ccrm-022 SD5: the key is (or was) an overseas student document's file -- in either stored shape, current, archived or replaced."""
    if key.startswith(f"{STORAGE_PREFIX}/"):
        return True
    shapes = (key, f"/{key}", f"/local-files/{key}")
    if await db.scalar(select(StudentDocument.id).where(StudentDocument.file_url.in_(shapes)).limit(1)):
        return True
    return bool(await db.scalar(select(DocumentEvent.id).where(DocumentEvent.file_key.in_(shapes)).limit(1)))


async def _withheld(db: AsyncSession, key: str) -> bool:
    """Keys only their own scope-checked routes hand out: KYC files (AGN-024) and overseas documents (ccrm-022 SD5)."""
    return key.startswith("agent-kyc/") or await _overseas_document(db, key)


@router.get("/download")
async def download(key: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if ".." in key or key.startswith(("/", "\\")):
        raise HTTPException(422, "Invalid object key")
    if await _withheld(db, key):
        raise HTTPException(404, "Not found")
    return {"url": storage.presign_download(key), "expires_in": 900 if settings.aws_s3_bucket else None}


@router.get("/signed/{token}")
async def signed_download(token: str):
    """nehn-003 PS2: the local-mode equivalent of an S3 presigned URL -- the route that issued the token did the authorisation."""
    key = storage.signed_key(token)
    if key is None or storage.bucket:
        raise HTTPException(404, "Not found")
    return _local_response(key)


@router.get("/{file_id}")
async def stored_file(file_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.get(StoredFile, file_id)
    if row is None:
        raise HTTPException(404, "File not found")
    if row.owner_id != user.id and user.role != "super_admin":
        raise HTTPException(403, "This file belongs to someone else")
    if storage.bucket:
        return RedirectResponse(storage.presign_download(row.key), status_code=307)
    return _local_response(row.key, filename=row.original_filename, media_type=row.content_type)


@local_router.get("/local-files/{key:path}")
async def local_files(key: str, edusphere_access: str | None = Cookie(default=None), db: AsyncSession = Depends(get_db)):
    """nehn-003 PS3: compatibility for `/local-files/...` URLs stored in rows. `public/` is open; any other key needs a session (404
    without one, so nothing is confirmed to exist) and follows the `/files/download` rules."""
    key = key.replace("\\", "/").lstrip("/")
    if not key.startswith(PUBLIC_PREFIXES):
        try:
            await get_current_user(edusphere_access, db)
        except HTTPException:
            raise HTTPException(404, "Not found") from None
        if await _withheld(db, key):
            raise HTTPException(404, "Not found")
    return _local_response(key)
