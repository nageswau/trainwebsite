"""ENH-029 -- bulk school partner onboarding (docs/superpowers/specs/2026-10-01-enh-029-bulk-school-onboarding-design.md,
DEC-SCOPE-044).

Each accepted CSV row creates exactly what `POST /overseas-admin/schools` creates, through the same `admin._provision_school`.
One request = one transaction with a savepoint per row, on ENH-028's batch/row tables (`target_type = 'school_onboarding'`);
welcome links go out after the commit. Its own router so `admin.py` does not grow; imports from `admin`/`school_bulk` only.
"""

import csv
import io
import time

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.school_bulk import _read_csv, _read_upload
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import User
from app.schemas import SchoolCreate

logger = get_logger(__name__)
router = APIRouter(prefix="/overseas-admin", tags=["school-onboarding-bulk"])

TARGET_TYPE = "school_onboarding"
ADMIN_ROLES = {"overseas_admin", "super_admin"}
COLUMNS = tuple(SchoolCreate.model_fields)  # D1: the template is exactly the single create's fields, in order
REQUIRED = ("name", "coordinator_full_name", "coordinator_email")
MAX_ROWS = 100


def _require_admin(user: User) -> None:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(403, "Overseas Admin role required")


@router.get("/schools/bulk-template")
async def bulk_onboarding_template(user: User = Depends(get_current_user)):
    _require_admin(user)
    buffer = io.StringIO()
    csv.writer(buffer).writerow(COLUMNS)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=school-onboarding-bulk-template.csv", "Cache-Control": "private, no-store"},
    )


@router.post("/schools/bulk-upload", status_code=201)
async def bulk_onboard_schools(
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    started = time.monotonic()
    _require_admin(user)
    raw = await _read_upload(file, idempotency_key, TARGET_TYPE, user)
    filled = _read_csv(raw, target_type=TARGET_TYPE, user=user, required=REQUIRED, columns=COLUMNS, max_rows=MAX_ROWS, known=COLUMNS)
    raise HTTPException(501, f"{len(filled)} rows parsed in {time.monotonic() - started:.3f}s")  # rows are processed in Task 5
