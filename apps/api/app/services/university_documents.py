"""upc-026 (DEC-SCOPE-139, spec §1-§3): the university document centre -- kinds, who sees which documents, files, versions and output.

Functions only; nothing here commits -- the route owns the transaction. Access reuses the University Master's (upc-003):
- the partnership roles and super_admin (CONTACT_ROLES) read every document and write within the master's edit scope (DC8);
- overseas_admin reads the `shareable` slice only (DC7); counselors get the same slice in upc-030;
- the commission agreement is stripped for every role without commission access, whatever else applies (DC2, U2).
A document the caller may not see is a 404 (never a 403), so its existence does not leak. Logs and audit rows carry ids only.
"""

import hashlib
import io
import logging
import zipfile
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import UNIVERSITY_DOCUMENT_KINDS, AuditLog, University, UniversityDocument, UniversityDocumentVersion, User
from app.services.image_metadata import JPEG, PNG, InvalidImage, detect_image_type, strip_metadata
from app.services.partnership_access import can_see_commission
from app.services.partnership_universities import CONTACT_ROLES
from app.services.storage import storage
from app.services.telecaller import person_ref

logger = logging.getLogger("app.partnership")

KINDS = UNIVERSITY_DOCUMENT_KINDS
COMMISSION_KIND = "commission_agreement"
# DC3 (Q-26): what a counsellor-facing reader may see unless the uploader says otherwise. The commission agreement is never shareable.
SHAREABLE_BY_DEFAULT = frozenset({"brochure", "course_list", "fee_structure", "entry_requirements", "scholarship_information", "marketing_materials", "application_guidelines", "training_documents"})
MAX_DOCUMENTS = 200  # per university (DC6)
MAX_VERSIONS = 50  # per document (DC6)
STORAGE_PREFIX = "university-documents"

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
EXTENSION = {PDF: "pdf", DOCX: "docx", XLSX: "xlsx", PPTX: "pptx", JPEG: "jpg", PNG: "png"}
OOXML_PARTS = {"word/document.xml": DOCX, "xl/workbook.xml": XLSX, "ppt/presentation.xml": PPTX}

NOT_FOUND = "Document not found"
WRONG_FILE = "Upload a PDF, Word, Excel, PowerPoint, JPEG or PNG file"
COMMISSION_SHAREABLE = "A commission agreement can never be shared with counsellors"
TITLE_TAKEN = "This university already has a document of this kind with this title -- upload a new version of it instead"
ORDER = (case({k: i for i, k in enumerate(KINDS)}, value=UniversityDocument.kind), func.lower(UniversityDocument.title), UniversityDocument.id)


def full_view(user: User) -> bool:
    return user.role in CONTACT_ROLES


def visibility(user: User) -> list:
    """Which documents this reader sees -- not by university: the caller adds that (one university, or all on the menu page)."""
    filters = []
    if not can_see_commission(user):
        filters.append(UniversityDocument.kind != COMMISSION_KIND)
    if not full_view(user):
        filters.append(UniversityDocument.shareable.is_(True))
    return filters


def default_shareable(kind: str) -> bool:
    return kind in SHAREABLE_BY_DEFAULT


def check_shareable(kind: str, shareable: bool) -> None:
    if kind == COMMISSION_KIND and shareable:
        raise HTTPException(422, COMMISSION_SHAREABLE)


async def load(db: AsyncSession, user: User, university_id: UUID, document_id: UUID, *, lock: bool = False) -> UniversityDocument:
    stmt = select(UniversityDocument).where(UniversityDocument.id == document_id, UniversityDocument.university_id == university_id, *visibility(user))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    document = await db.scalar(stmt)
    if document is None:
        raise HTTPException(404, NOT_FOUND)
    return document


async def count(db: AsyncSession, university_id: UUID) -> int:
    return await db.scalar(select(func.count()).select_from(UniversityDocument).where(UniversityDocument.university_id == university_id)) or 0


async def check_title_free(db: AsyncSession, university_id: UUID, kind: str, title: str, document_id: UUID | None = None) -> None:
    """DC11, under the university lock (uq_university_documents_title is the backstop). Checked across every document, hidden ones too."""
    stmt = select(UniversityDocument.id).where(UniversityDocument.university_id == university_id, UniversityDocument.kind == kind, func.lower(UniversityDocument.title) == title.lower())
    if document_id is not None:
        stmt = stmt.where(UniversityDocument.id != document_id)
    if await db.scalar(stmt.limit(1)):
        raise HTTPException(409, TITLE_TAKEN)


# --- files (DC4, DC5, DC14) ---------------------------------------------------------------------------------------------------
def _ooxml_type(data: bytes) -> str | None:
    """An Office file is a ZIP with its main part; only the central directory is read, nothing is extracted."""
    if not data.startswith(b"PK\x03\x04"):
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return None
    return next((content_type for part, content_type in OOXML_PARTS.items() if part in names), None)


async def read_file(file: UploadFile) -> tuple[bytes, str, str | None]:
    """The type is decided by the bytes, never by the name or the client's Content-Type; image metadata is stripped (AGN-009 G8).
    Returns (bytes, content type, display name)."""
    data = await file.read(settings.max_upload_bytes + 1)
    if not data:
        raise HTTPException(422, "The file is empty")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"The file must be at most {max(1, settings.max_upload_bytes // (1024 * 1024))} MB")
    content_type = PDF if data.startswith(b"%PDF-") else detect_image_type(data) or _ooxml_type(data)
    if content_type is None:
        raise HTTPException(422, WRONG_FILE)
    if content_type in (JPEG, PNG):
        try:
            data = strip_metadata(data, content_type)
        except InvalidImage:
            raise HTTPException(422, "The image could not be read as a valid JPEG or PNG") from None
    name = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1][:255] or None  # display only; never part of a storage path
    return data, content_type, name


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def store(data: bytes, content_type: str) -> str:
    """A server-generated key; the client never names a path. 500 (logged by key digest) when storage fails."""
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("university_document_store_failed", extra={"extra_fields": {"key_digest": _digest(key)}})
        raise HTTPException(500, "Could not store the file; please try again") from None
    return key


def discard(key: str) -> None:
    """Delete an object stored for a write that did not commit; only this module's keys. A failure leaves a logged orphan."""
    if not key.startswith(f"{STORAGE_PREFIX}/"):
        return
    try:
        storage.delete(key)
    except Exception:
        logger.warning("university_document_orphaned", extra={"extra_fields": {"key_digest": _digest(key)}})


def file_bytes(version: UniversityDocumentVersion) -> bytes:
    try:
        return storage.read_bytes(version.storage_key)
    except FileNotFoundError:
        logger.warning("university_document_file_missing", extra={"extra_fields": {"key_digest": _digest(version.storage_key)}})
        raise HTTPException(404, "Document file not found") from None


def add_version(db: AsyncSession, user: User, document: UniversityDocument, version: int, stored: dict) -> None:
    db.add(UniversityDocumentVersion(document_id=document.id, version=version, uploaded_by_user_id=user.id, **stored))


def download_name(university: University, document: UniversityDocument, version: UniversityDocumentVersion) -> str:
    """DC10: built from server values only -- never the uploaded name or the title (no header injection)."""
    return f"{university.university_code}-{document.kind}-v{version.version}.{EXTENSION.get(version.content_type, 'bin')}"


# --- output ---------------------------------------------------------------------------------------------------------------
def _university_ref(university: University) -> dict:
    return {"id": university.id, "name": university.name, "university_code": university.university_code}


async def documents_out(db: AsyncSession, rows: list[tuple[UniversityDocument, University]]) -> list[dict]:
    """Each document with its versions (newest first) and who uploaded them; two queries for the whole page."""
    ids = [document.id for document, _ in rows]
    versions = (await db.scalars(select(UniversityDocumentVersion).where(UniversityDocumentVersion.document_id.in_(ids)).order_by(UniversityDocumentVersion.version.desc()))).all() if ids else []
    user_ids = {v.uploaded_by_user_id for v in versions}
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(user_ids)))).all()} if user_ids else {}
    by_document: dict[UUID, list[dict]] = {}
    for v in versions:
        by_document.setdefault(v.document_id, []).append(
            {
                "version": v.version,
                "file_name": v.file_name,
                "content_type": v.content_type,
                "size_bytes": v.size_bytes,
                "uploaded_by": person_ref(people[v.uploaded_by_user_id]),
                "uploaded_at": v.uploaded_at,
            }
        )
    return [
        {
            "id": d.id,
            "university": _university_ref(u),
            "kind": d.kind,
            "title": d.title,
            "shareable": d.shareable,
            "current_version": d.current_version,
            "versions": by_document.get(d.id, []),
            "created_at": d.created_at,
            "updated_at": d.updated_at,
        }
        for d, u in rows
    ]


async def document_out(db: AsyncSession, document: UniversityDocument, university: University) -> dict:
    await db.refresh(document)  # server defaults (timestamps) are expired after a flush
    return (await documents_out(db, [(document, university)]))[0]


def audit(db: AsyncSession, user: User, action: str, document: UniversityDocument, **metadata) -> None:
    """Same transaction as the write (fail closed); ids, kind, version and field names only (DC13)."""
    metadata = {"university_id": str(document.university_id), "kind": document.kind, **metadata}
    db.add(AuditLog(user_id=user.id, action=f"university_document.{action}", entity_type="university_document", entity_id=str(document.id), metadata_json=metadata))


def log(event: str, user: User, document: UniversityDocument, **extra) -> None:
    logger.info(
        event,
        extra={"extra_fields": {"actor_id": str(user.id), "document_id": str(document.id), "university_id": str(document.university_id), **extra}},
    )
