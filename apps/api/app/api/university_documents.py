"""upc-026 (DEC-SCOPE-139, spec §3): the university document centre -- list, upload, new version, edit, download, and the menu list.

Every write: the read gate (`require_reader`, 403), the university (404) and its `can_manage_documents` (403 role/team, 409 inactive),
all before a byte is read; then the file is sniffed and stored, the university row is locked (FOR UPDATE serialises the limits, titles
and version numbers), the checks re-run, the rows and the audit row are written and committed once here. On any failure the stored
object is discarded (DC14). A download is audited and committed before any byte leaves (DC10)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic_core import PydanticCustomError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import OFFSET
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.api.portfolio_certificates import HEADERS
from app.core.database import get_db
from app.models import UNIVERSITY_DOCUMENT_KINDS, University, UniversityDocument, UniversityDocumentVersion, User
from app.schemas import UniversityDocumentUpdate, university_document_title
from app.services import partnership_universities as unis
from app.services import university_documents as svc

router = APIRouter(prefix="/partnership", tags=["partnership-universities"])
Kind = Literal[UNIVERSITY_DOCUMENT_KINDS]


async def _writable(db: AsyncSession, user: User, university_id: UUID, route: str, *, lock: bool = False) -> University:
    uni = await unis.load(db, university_id, lock=lock)
    unis.require(user, uni, await unis.team_of(db, user), "can_manage_documents", route)
    return uni


def _title(value: str) -> str:
    try:
        return university_document_title(value)
    except PydanticCustomError as error:
        raise HTTPException(422, str(error)) from None


async def _page(db: AsyncSession, filters: list, order, limit: int, offset: int) -> dict:
    base = select(UniversityDocument, University).join(University, University.id == UniversityDocument.university_id).where(*filters)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = [(d, u) for d, u in (await db.execute(base.order_by(*order).limit(limit).offset(offset))).tuples().all()]
    return {"items": await svc.documents_out(db, rows), "total": total or 0, "limit": limit, "offset": offset}


@router.get("/universities/{university_id}/documents")
async def list_documents(
    university_id: UUID,
    kind: Kind | None = None,
    limit: int = Query(svc.MAX_DOCUMENTS, ge=1, le=svc.MAX_DOCUMENTS),
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """In §28's kind order, then by title. The reader's slice only (DC2, DC7)."""
    await unis.require_reader(db, user)
    await unis.load(db, university_id)
    filters = [UniversityDocument.university_id == university_id, *svc.visibility(user)] + ([UniversityDocument.kind == kind] if kind else [])
    return await _page(db, filters, svc.ORDER, limit, offset)


@router.get("/documents")
async def menu_documents(
    kind: Kind | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=50),
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DC12: every document the reader may see, across universities, newest change first; `q` matches the title or the university."""
    await unis.require_reader(db, user)
    filters = svc.visibility(user) + ([UniversityDocument.kind == kind] if kind else [])
    if (pattern := like_pattern(q)) is not None:
        filters.append(or_(*(c.ilike(pattern, escape="\\") for c in (UniversityDocument.title, University.name, University.university_code))))
    return await _page(db, filters, (UniversityDocument.updated_at.desc(), UniversityDocument.id), limit, offset)


@router.post("/universities/{university_id}/documents", status_code=201)
async def upload_document(
    university_id: UUID,
    kind: Kind = Form(...),
    title: str = Form(...),
    shareable: bool | None = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Version 1 of a new document. `shareable` omitted = the kind's default (DC3); the commission agreement is always internal (DC2)."""
    await unis.require_reader(db, user)
    await _writable(db, user, university_id, "document_create")
    title = _title(title)
    shareable = svc.default_shareable(kind) if shareable is None else shareable
    svc.check_shareable(kind, shareable)
    data, content_type, file_name = await svc.read_file(file)
    key = svc.store(data, content_type)
    try:
        uni = await _writable(db, user, university_id, "document_create", lock=True)
        if await svc.count(db, uni.id) >= svc.MAX_DOCUMENTS:
            raise HTTPException(409, f"A university can have at most {svc.MAX_DOCUMENTS} documents")
        await svc.check_title_free(db, uni.id, kind, title)
        document = UniversityDocument(university_id=uni.id, kind=kind, title=title, shareable=shareable, current_version=1, created_by_user_id=user.id)
        db.add(document)
        await db.flush()
        svc.add_version(db, user, document, 1, {"storage_key": key, "file_name": file_name, "content_type": content_type, "size_bytes": len(data)})
        svc.audit(db, user, "upload", document, version=1, content_type=content_type, size_bytes=len(data), shareable=shareable)
        await db.commit()
    except Exception:  # a refusal, a lost race on a unique index, or a failed commit: nothing references the stored file
        await db.rollback()
        svc.discard(key)
        raise
    svc.log("university_document_uploaded", user, document, version=1)
    return {"document": await svc.document_out(db, document, uni)}


@router.post("/universities/{university_id}/documents/{document_id}/versions", status_code=201)
async def upload_version(university_id: UUID, document_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """DC6: the file becomes version n+1 and current; earlier versions stay downloadable."""
    await unis.require_reader(db, user)
    await _writable(db, user, university_id, "document_version")
    await svc.load(db, user, university_id, document_id)
    data, content_type, file_name = await svc.read_file(file)
    key = svc.store(data, content_type)
    try:
        uni = await _writable(db, user, university_id, "document_version", lock=True)
        document = await svc.load(db, user, uni.id, document_id, lock=True)
        if document.current_version >= svc.MAX_VERSIONS:
            raise HTTPException(409, f"A document can have at most {svc.MAX_VERSIONS} versions")
        version = document.current_version + 1
        svc.add_version(db, user, document, version, {"storage_key": key, "file_name": file_name, "content_type": content_type, "size_bytes": len(data)})
        document.current_version = version  # TimestampMixin moves updated_at (the menu list's order)
        svc.audit(db, user, "version", document, version=version, content_type=content_type, size_bytes=len(data))
        await db.commit()
    except Exception:
        await db.rollback()
        svc.discard(key)
        raise
    svc.log("university_document_versioned", user, document, version=version)
    return {"document": await svc.document_out(db, document, uni)}


@router.patch("/universities/{university_id}/documents/{document_id}")
async def update_document(university_id: UUID, document_id: UUID, payload: UniversityDocumentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Title and shareable only; a value equal to the stored one is not a change (no audit)."""
    await unis.require_reader(db, user)
    uni = await _writable(db, user, university_id, "document_update", lock=True)
    document = await svc.load(db, user, uni.id, document_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    changed = sorted(k for k, v in changes.items() if getattr(document, k) != v)
    if "shareable" in changed:
        svc.check_shareable(document.kind, changes["shareable"])
    if "title" in changed:
        await svc.check_title_free(db, uni.id, document.kind, changes["title"], document.id)
    for key in changed:
        setattr(document, key, changes[key])
    if changed:
        svc.audit(db, user, "update", document, fields=changed)
    await db.commit()
    if changed:
        svc.log("university_document_updated", user, document, fields=changed)
    return {"document": await svc.document_out(db, document, uni)}


@router.get("/universities/{university_id}/documents/{document_id}/file")
async def download_document(
    university_id: UUID,
    document_id: UUID,
    version: int | None = Query(None, ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DC10: readers who can see the document; the current version unless `version` is given. Audited before any byte leaves."""
    await unis.require_reader(db, user)
    uni = await unis.load(db, university_id)
    document = await svc.load(db, user, uni.id, document_id)
    number = version or document.current_version
    stored = await db.scalar(select(UniversityDocumentVersion).where(UniversityDocumentVersion.document_id == document.id, UniversityDocumentVersion.version == number))
    if stored is None:
        raise HTTPException(404, "This document has no such version")
    data = svc.file_bytes(stored)
    svc.audit(db, user, "download", document, version=number, role=user.role)
    await db.commit()
    svc.log("university_document_downloaded", user, document, version=number)
    disposition = f'attachment; filename="{svc.download_name(uni, document, stored)}"'
    return Response(content=data, media_type=stored.content_type, headers={**HEADERS, "Content-Disposition": disposition})
