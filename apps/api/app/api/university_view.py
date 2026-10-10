"""upc-030 (DEC-SCOPE-161, spec §4): the University 360 view for counselors, overseas_admin, BDMs and university reps (U14).

The role gate is first (403), then the university in the slice's scope (404, never 403, so an internal university does not leak). A
document download is for the slices that list documents; it is audited and committed before any byte leaves (upc-026 DC10)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.portfolio_certificates import HEADERS
from app.core.database import get_db
from app.models import UniversityDocumentVersion, User
from app.services import university_documents as documents
from app.services import university_view as svc

router = APIRouter(prefix="/universities", tags=["university-view"])


@router.get("/{university_id}/view")
async def university_view(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    slice_name = await svc.slice_of(db, user)
    return await svc.view_out(db, user, slice_name, await svc.visible_university(db, user, slice_name, university_id))


@router.get("/{university_id}/view/documents/{document_id}/file")
async def view_document_file(university_id: UUID, document_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """UV9: the current version of a document this slice lists; any other document is a 404."""
    slice_name = await svc.slice_of(db, user)
    if "documents" not in svc.SECTIONS[slice_name]:
        raise HTTPException(403, svc.REFUSED)
    uni = await svc.visible_university(db, user, slice_name, university_id)
    document = await documents.load(db, user, uni.id, document_id)
    stored = await db.scalar(select(UniversityDocumentVersion).where(UniversityDocumentVersion.document_id == document.id, UniversityDocumentVersion.version == document.current_version))
    if stored is None:
        raise HTTPException(404, documents.NOT_FOUND)
    data = documents.file_bytes(stored)
    documents.audit(db, user, "download", document, version=stored.version, role=user.role)
    await db.commit()
    documents.log("university_document_downloaded", user, document, version=stored.version)
    disposition = f'attachment; filename="{documents.download_name(uni, document, stored)}"'
    return Response(content=data, media_type=stored.content_type, headers={**HEADERS, "Content-Disposition": disposition})
