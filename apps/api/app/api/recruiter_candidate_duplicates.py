"""hrc-014 (DEC-SCOPE-377 D2/D3/D9): the probable-duplicate review queue -- list, "Check the whole pool", and "Not the same person".
Candidate writers holding `candidates.merge` only; the merge itself lives with the candidate (`/recruiter/candidates/{id}/merge`).
Each write is one transaction committed here."""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE
from app.api.bdm import LIMIT, OFFSET
from app.api.deps import get_current_user
from app.api.telecaller_catalogue import NOT_AN_OBJECT
from app.core.database import get_db
from app.models import User
from app.schemas import CANDIDATE_MERGE_LABELS, CandidateDuplicateDismiss, CandidateDuplicateStatus
from app.services import candidate_duplicates as svc
from app.services.telecaller import _parse

router = APIRouter(prefix="/recruiter/candidate-duplicates", tags=["recruiter-candidate-duplicates"])


@router.get("")
async def list_pairs(response: Response, status: CandidateDuplicateStatus = "open", limit: int = LIMIT, offset: int = OFFSET,
                     user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Open pairs oldest first; reviewed ones newest decision first. Names, codes and the matched signals -- no contact data."""
    await svc.require_merger(db, user)
    response.headers.update(NO_STORE)
    return await svc.queue(db, status, limit, offset)


@router.post("/scan")
async def scan(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Queue every probable pair in the pool not queued yet (finds pairs that existed before hrc-014)."""
    await svc.require_merger(db, user)
    created = await svc.detect(db)
    await db.commit()
    return {"created": created}


@router.post("/{pair_id}/dismiss")
async def dismiss(pair_id: UUID, payload: dict = Body(default_factory=dict), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """"Not the same person": closed for good, with an optional note kept on the pair (never on the audit row)."""
    await svc.require_merger(db, user)
    body = _parse(CandidateDuplicateDismiss, payload, NOT_AN_OBJECT, CANDIDATE_MERGE_LABELS)
    result = await svc.dismiss(db, user, pair_id, body.note)
    await db.commit()
    return result
