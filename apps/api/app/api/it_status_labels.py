"""itc-005 (DEC-SCOPE-362; API §12JH; RBAC §2.262) -- the IT team's status labels. Every IT staff user (and super_admin) reads the
catalogue the screens label leads with; the IT Admin reads it with usage counts and saves one status at a time (audited)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.schemas import ItStatusLabelIn
from app.services import it_status_labels as svc

router = APIRouter(prefix="/it/status-labels", tags=["it-status-labels"])
admin_router = APIRouter(prefix="/admin/it/status-labels", tags=["it-status-labels"])


@router.get("")
async def read_labels(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_reader(user)
    return await svc.catalogue(db)


@admin_router.get("")
async def read_admin_labels(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_admin(user)
    return await svc.admin_catalogue(db)


@admin_router.put("/{kind}/{code}")
async def save_label(kind: str, code: str, payload: ItStatusLabelIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """An idempotent replace of one status's override, hence 200."""
    return await svc.save(db, user, kind, code, payload.label, payload.sort_order, payload.enabled)
