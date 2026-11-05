"""pob-003 (DEC-SCOPE-406 D6-D8): a company's document store. Mounted under the rec-003 company router (`/recruiter/companies`).

Every `{company_id}` resolves through `recruiter_companies.load_scoped` (out of scope = 404; a non-recruiter role = 403). An upload checks
scope and role before reading the bytes, then re-checks under the company lock; the stored object is deleted when anything after storing it
fails. A download's audit row is committed before any byte leaves."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.portfolio_certificates import EXTENSION, HEADERS
from app.core.database import get_db
from app.models import CompanyDocument, User
from app.schemas import RecCompanyDocumentEnvelope, RecCompanyDocumentKind, RecCompanyDocumentPage
from app.services import company_documents as svc
from app.services import recruiter_companies as companies
from app.services import recruiter_contracts as contracts
from app.services.agent_documents import read_upload

router = APIRouter(tags=["recruiter-company-documents"])


@router.get("/{company_id}/documents", response_model=RecCompanyDocumentPage)
async def list_documents(
    company_id: UUID,
    kind: RecCompanyDocumentKind | None = None,
    meeting_id: UUID | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    company = await companies.load_scoped(db, user, company_id)
    return await svc.page(db, user, company, kind, meeting_id, limit, offset)


@router.post("/{company_id}/documents", status_code=201, response_model=RecCompanyDocumentEnvelope)
async def upload_document(
    company_id: UUID,
    kind: Annotated[RecCompanyDocumentKind, Form()],
    file: Annotated[UploadFile, File()],
    meeting_id: Annotated[UUID | None, Form()] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    companies.require(user, await companies.load_scoped(db, user, company_id), "can_edit", "company_document")
    data, content_type, name = await read_upload(file)
    company = await companies.load_scoped(db, user, company_id, lock=True)
    companies.require(user, company, "can_edit", "company_document")
    await svc.check_upload(db, user, company, kind, meeting_id)
    key = svc.store(data, content_type)
    try:
        document = CompanyDocument(company_id=company.id, kind=kind, name=name, content_type=content_type, size_bytes=len(data), storage_key=key,
                                   meeting_id=meeting_id, uploaded_by_user_id=user.id)  # fmt: skip
        db.add(document)
        await db.flush()
        svc.audit(db, user, "uploaded", document, {"content_type": content_type, "bytes": len(data), "meeting_id": str(meeting_id) if meeting_id else None})
        await db.commit()
    except BaseException:
        await db.rollback()
        svc.discard(key)
        raise
    svc.log("recruiter_company_document_uploaded", user, company.id, document_id=str(document.id), kind=kind, content_type=content_type, bytes=len(data))
    return {"document": await svc.one(db, user, document.id)}


@router.get("/documents/{document_id}/download")
async def download_document(document_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """In the company's read scope only (404 otherwise, as an unknown id); an agreement needs `commercials.client.view` (403, after the
    scope check). The file name is built from the company code and the kind, never the uploaded name."""
    document, company = await svc.load_scoped(db, user, document_id)
    if document.kind == svc.AGREEMENT:
        await contracts.require_terms(db, user, "company_document_download", edit=False)
    data = svc.read(document)
    filename = f"{document.kind.replace('_', '-')}-{company.company_code}.{EXTENSION.get(document.content_type, 'bin')}"
    svc.audit(db, user, "downloaded", document, {"role": user.role})
    await db.commit()
    svc.log("recruiter_company_document_downloaded", user, company.id, document_id=str(document.id), kind=document.kind, role=user.role)
    return Response(content=data, media_type=document.content_type, headers={**HEADERS, "Content-Disposition": f'attachment; filename="{filename}"'})
