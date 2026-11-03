"""itc-030 (DEC-SCOPE-367; API §12JM; RBAC §2.267): GET /counselor/it/dashboard -- the IT counselor's dashboard over their own book, and the
IT Admin's over every IT counselor's (narrowed by `owner`). The request names no student or lead, so there is nothing to tamper with;
anyone else is 403. Read only, never cached, not audited (services/it_counselor_dashboard.py)."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_reports import NO_STORE
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import it_counselor_dashboard
from app.services.bdm_appointments import db_now

router = APIRouter(prefix="/counselor/it", tags=["it-counselor-dashboard"])


@router.get("/dashboard")
async def it_dashboard(
    response: Response, program: str | None = None, batch: str | None = None, date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"), stage: str | None = None, owner: str | None = None,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):  # fmt: skip
    response.headers.update(NO_STORE)
    return await it_counselor_dashboard.dashboard(db, user, await db_now(db), program=program, batch=batch, date_from=date_from, date_to=date_to, stage=stage, owner=owner)
