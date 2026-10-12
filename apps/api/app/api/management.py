"""mgmt-001: the Management Command Center's own routes. Every later mgmt item adds its routes here or beside it, each asking
`services/management_access` for its tier first (M13)."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models import User
from app.schemas import ManagementMeOut
from app.services.management_access import require_management, tiers

router = APIRouter(prefix="/management", tags=["management"])


@router.get("/me", response_model=ManagementMeOut)
async def management_me(user: User = Depends(get_current_user)):
    """The caller and the tiers they may see: partner (all), accountant (finance), super_admin (operational); anyone else 403."""
    require_management(user)
    return {"id": user.id, "full_name": user.full_name, "role": user.role, "tiers": tiers(user)}
