"""AGN-024 (DEC-SCOPE-224): KYC documents of a self-registered agency.

`admin_router` -- Overseas Admin and Super Admin review each document (K3, K7); the role gate runs before any lookup. Files are
streamed (never a presigned or /local-files URL), never cached, and every view is audited. `router` -- a pending agency's Master sees
its own documents and replaces rejected ones (K5); it deliberately skips `agent_denial_reason`, which refuses pending agencies.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AgentOrg, AgentOrgKycDocument, AuditLog, User
from app.schemas import KycRejectRequest
from app.services import agent_kyc as kyc
from app.services.agent_orgs import lock_org
from app.services.storage import storage

admin_router = APIRouter(prefix="/overseas-admin", tags=["agent-kyc"])
router = APIRouter(prefix="/agent/registration", tags=["agent-kyc"])

ADMIN_ROLES = {"overseas_admin", "super_admin"}
NO_STORE = {"Cache-Control": "no-store"}


def _require_admin(user: User) -> None:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Overseas Admin role required")


def _audit(db: AsyncSession, actor: User, action: str, doc: AgentOrgKycDocument, outcome: str | None = None) -> None:
    db.add(AuditLog(user_id=actor.id, action=action, entity_type="agent_org_kyc_document", entity_id=str(doc.id), outcome=outcome,
                    metadata_json={"org_id": str(doc.org_id), "doc_type": doc.doc_type}))  # fmt: skip  # never the number


async def _doc(db: AsyncSession, org_id: UUID, doc_id: UUID) -> AgentOrgKycDocument:
    doc = await db.scalar(select(AgentOrgKycDocument).where(AgentOrgKycDocument.id == doc_id, AgentOrgKycDocument.org_id == org_id))
    if doc is None:
        raise HTTPException(404, "Document not found")
    return doc


@admin_router.get("/agent-orgs/{org_id}/kyc-documents")
async def list_kyc_documents(org_id: UUID, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(user)
    org = await db.get(AgentOrg, org_id)
    if org is None:
        raise HTTPException(404, "Agent organisation not found")
    response.headers.update(NO_STORE)
    return {"kyc_required": org.kyc_required, "org_status": org.status, "items": [kyc.admin_view(d) for d in await kyc.documents(db, org.id)]}


@admin_router.get("/agent-orgs/{org_id}/kyc-documents/{doc_id}/file")
async def view_kyc_file(org_id: UUID, doc_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(user)
    doc = await _doc(db, org_id, doc_id)
    try:
        data = storage.read_bytes(doc.file_key)
    except Exception:
        raise HTTPException(500, "Could not read the file; please try again") from None
    _audit(db, user, "agent_kyc.view", doc)
    await db.commit()
    headers = {**NO_STORE, "Content-Disposition": f'inline; filename="{kyc.download_name(doc)}"', "X-Content-Type-Options": "nosniff"}
    return Response(content=data, media_type=doc.content_type, headers=headers)


async def _review(db: AsyncSession, org_id: UUID, doc_id: UUID, actor: User) -> tuple[AgentOrg, AgentOrgKycDocument]:
    org = await lock_org(db, org_id)  # serialises with approve/reject of the org
    doc = await _doc(db, org.id, doc_id)
    if org.status != "pending":
        raise HTTPException(409, kyc.NOT_PENDING_REVIEW)
    doc.reviewed_by_user_id = actor.id
    doc.reviewed_at = datetime.now(UTC)
    return org, doc


@admin_router.post("/agent-orgs/{org_id}/kyc-documents/{doc_id}/verify")
async def verify_kyc_document(org_id: UUID, doc_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(user)
    _org, doc = await _review(db, org_id, doc_id, user)
    doc.status, doc.rejection_reason = "verified", None
    _audit(db, user, "agent_kyc.verify", doc, "verified")
    await db.commit()
    await db.refresh(doc)
    return kyc.admin_view(doc)


@admin_router.post("/agent-orgs/{org_id}/kyc-documents/{doc_id}/reject")
async def reject_kyc_document(org_id: UUID, doc_id: UUID, payload: KycRejectRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _require_admin(user)
    org, doc = await _review(db, org_id, doc_id, user)
    doc.status, doc.rejection_reason = "rejected", payload.reason
    _audit(db, user, "agent_kyc.reject", doc, "rejected")
    await kyc.notify_rejected(db, org.id, doc)  # K6: rides this transaction
    await db.commit()
    await db.refresh(doc)
    return kyc.admin_view(doc)
