"""tel-020 (DEC-SCOPE-110 AL1, AL11; API §12AD): each team's alert thresholds -- Lead Not Contacted and Hot Lead Pending, in whole hours.
Any telecaller manager or super_admin reads and sets both teams (the tel-022 G3 rule for team defaults); every other role is 403. The beat
reads the rows on every run, so a change applies from the next run (AC4).

Inline checks per the 2026-09-28 convention: role first, then the team (an unknown one is 404), then the body."""

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AuditLog, TelSetting, User
from app.schemas import TEL_SETTING_FIELD_LABELS, TelSettingsOut, TelSettingsPage, TelSettingsUpdate
from app.services.telecaller import TEAM_LABEL, TEAMS, _parse, require_manager

router = APIRouter(prefix="/telecaller", tags=["telecaller-settings"])
FIELDS = tuple(TEL_SETTING_FIELD_LABELS)


async def _out(db: AsyncSession, row: TelSetting) -> dict:
    by = await db.get(User, row.updated_by_user_id) if row.updated_by_user_id else None
    return {"team": row.team, "team_label": TEAM_LABEL[row.team], **{f: getattr(row, f) for f in FIELDS}, "updated_at": row.updated_at,
            "updated_by": {"id": by.id, "full_name": by.full_name} if by else None}


@router.get("/settings", response_model=TelSettingsPage)
async def get_settings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    rows = await db.scalars(select(TelSetting).order_by(TelSetting.team))
    return {"items": [await _out(db, row) for row in rows]}


@router.put("/settings/{team}", response_model=TelSettingsOut)
async def set_settings(team: str, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """An idempotent replace of the team's row (seeded by 0099), hence 200; the row lock serialises two managers saving at once."""
    require_manager(user)
    row = await db.scalar(select(TelSetting).where(TelSetting.team == team).with_for_update()) if team in TEAMS else None
    if row is None:  # 0099 seeds both teams, so only an unknown team gets here
        raise HTTPException(404, "Team not found")
    data = _parse(TelSettingsUpdate, payload, "The request body must be an object", TEL_SETTING_FIELD_LABELS)
    before = {f: getattr(row, f) for f in FIELDS}
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    row.updated_by_user_id = user.id
    db.add(AuditLog(user_id=user.id, action="tel.settings.update", entity_type="tel_settings", entity_id=team,
                    metadata_json={"from": before, "to": data.model_dump()}))
    await db.commit()
    await db.refresh(row)
    return await _out(db, row)
