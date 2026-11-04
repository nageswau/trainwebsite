"""hrc-024 (DEC-SCOPE-393, API §12KL): the candidate routing settings and rules -- placement managers and super_admin only (R11), checked
before anything is read. Each write is one transaction: role, validation, change, audit row, one commit here. The unassigned queue and
manual assignment are hrc-012's (`GET /recruiter/candidates?owner=unassigned`, `PUT /recruiter/candidates/{id}/ownership`)."""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.telecaller_catalogue import NOT_AN_OBJECT
from app.core.database import get_db
from app.models import User
from app.schemas import CANDIDATE_ROUTING_LABELS, CandidateRoutingOut, CandidateRoutingRuleIn, CandidateRoutingRuleOut, CandidateRoutingSettingsIn
from app.services import candidate_routing as routing
from app.services.telecaller import _parse

router = APIRouter(prefix="/recruiter/candidate-routing", tags=["recruiter-candidates"])


def _body(model, payload):
    return _parse(model, payload, NOT_AN_OBJECT, CANDIDATE_ROUTING_LABELS)


@router.get("", response_model=CandidateRoutingOut)
async def routing_overview(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The settings and every rule in routing order (source, skill category, location; oldest first)."""
    routing.require_editor(user)
    return await routing.overview(db)


@router.put("", response_model=CandidateRoutingOut)
async def save_routing_settings(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    routing.require_editor(user)
    body = _body(CandidateRoutingSettingsIn, payload)
    await routing.save_settings(db, user, body.default_recruiter_user_id, body.strategy)
    await db.commit()
    return await routing.overview(db)


@router.post("/rules", response_model=CandidateRoutingRuleOut, status_code=201)
async def add_routing_rule(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    routing.require_editor(user)
    out = await routing.add_rule(db, user, _body(CandidateRoutingRuleIn, payload))
    await db.commit()
    return out


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_routing_rule(rule_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    routing.require_editor(user)
    await routing.delete_rule(db, user, rule_id)
    await db.commit()
    return Response(status_code=204)
