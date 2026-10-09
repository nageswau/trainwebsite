"""upc-008 (DEC-SCOPE-142, spec §3): a university's expected timeline (§5) and milestone tracker (§6).

Functions only; nothing here commits -- the route owns the transaction and the audit row. Milestone rows are sparse (MS2: the catalogue
is the template); statuses are computed on read in IST (Q-11, MS3) and three milestones are achieved by events, derived on read (MS4,
MS5): nothing writes them, so applications made before this item count too. Audit metadata carries kinds, field names and dates only.
"""

from datetime import date, datetime
from uuid import UUID

from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApplicationStatusHistory, OverseasApplication, University, UniversityMilestone, UniversityStageHistory, User
from app.partnership_milestones import ADMITTED_STATUS, AUTO_SOURCES, MILESTONES, PROPOSAL_STAGE
from app.partnership_stages import STAGE_KEYS
from app.schemas import UniversityExpectedUpdate, UniversityMilestoneUpdate
from app.services.bdm_appointments import IST
from app.services.bdm_travel import india_today

ACHIEVED_FUTURE = "The achieved date can't be in the future"
EXPECTED_FIELDS = ("target_partnership_date", "expected_intake", "expected_agreement_date", "expected_recruitment_start")


# --- §5 expected timeline -----------------------------------------------------------------------------------------------------
def expected_out(uni: University) -> dict:
    """Q-10 (MS8): month and quarter are derived from the target partnership date (calendar quarters), never stored."""
    target = uni.target_partnership_date
    return {
        **{f: getattr(uni, f) for f in EXPECTED_FIELDS},
        "expected_month": f"{target:%Y-%m}" if target else None,
        "expected_quarter": f"{target.year}-Q{(target.month - 1) // 3 + 1}" if target else None,
    }


def update_expected(uni: University, payload: UniversityExpectedUpdate) -> list[str]:
    """Only the fields sent; a value equal to the stored one is not a change. Returns the changed field names (for the audit)."""
    changes = payload.model_dump(include=payload.model_fields_set)
    changed = sorted(f for f, value in changes.items() if getattr(uni, f) != value)
    for field in changed:
        setattr(uni, field, changes[field])
    return changed


# --- §6 milestones -------------------------------------------------------------------------------------------------------------
async def _derived(db: AsyncSession, university_id: UUID) -> dict[str, date]:
    """MS4: the IST day of each achieving event -- one statement, three scalar subqueries on indexed columns."""
    proposal = (
        select(func.min(UniversityStageHistory.created_at))
        .where(
            UniversityStageHistory.university_id == university_id,
            UniversityStageHistory.kind == "move",
            UniversityStageHistory.to_stage.in_(STAGE_KEYS[STAGE_KEYS.index(PROPOSAL_STAGE) :]),
        )
        .scalar_subquery()
    )
    application = select(func.min(OverseasApplication.created_at)).where(OverseasApplication.university_id == university_id).scalar_subquery()
    admission = (
        select(func.min(ApplicationStatusHistory.created_at))
        .join(OverseasApplication, OverseasApplication.id == ApplicationStatusHistory.application_id)
        .where(OverseasApplication.university_id == university_id, ApplicationStatusHistory.to_status == ADMITTED_STATUS)
        .scalar_subquery()
    )
    row = (await db.execute(select(proposal, application, admission))).one()
    instants: dict[str, datetime | None] = dict(zip(("proposal", "first_application", "first_admission"), row, strict=True))
    return {kind: at.astimezone(IST).date() for kind, at in instants.items() if at is not None}


async def _rows(db: AsyncSession, university_id: UUID) -> dict[str, UniversityMilestone]:
    stmt = select(UniversityMilestone).where(UniversityMilestone.university_id == university_id)
    return {m.kind: m for m in (await db.scalars(stmt)).all()}


def _items(rows: dict[str, UniversityMilestone], derived: dict[str, date], today: date) -> list[dict]:
    """Q-11 (MS3): done when achieved; delayed when the target is before today; the earliest not-done one is in progress (unless
    delayed); the rest are pending. A recorded achieved date wins over the derived one (MS5)."""
    items = []
    reached_current = False
    for m in MILESTONES:
        row = rows.get(m.key)
        target, manual, auto = (row.target_date if row else None), (row.achieved_on if row else None), derived.get(m.key)
        achieved = manual or auto
        if achieved:
            status = "done"
        else:
            status = "delayed" if target and target < today else "pending" if reached_current else "in_progress"
            reached_current = True
        items.append({
            "kind": m.key, "label": m.label, "target_date": target, "achieved_on": achieved,
            "achieved_by": "manual" if manual else "auto" if auto else None, "auto_source": AUTO_SOURCES.get(m.key), "status": status,
        })  # fmt: skip
    return items


def _page(rows: dict[str, UniversityMilestone], derived: dict[str, date], today: date, can_edit: bool) -> dict:
    return {"items": _items(rows, derived, today), "today": today, "can_edit": can_edit}


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


async def page(db: AsyncSession, university_id: UUID, can_edit: bool) -> dict:
    return _page(await _rows(db, university_id), await _derived(db, university_id), india_today(), can_edit)


async def update(db: AsyncSession, user: User, uni: University, kind: str, payload: UniversityMilestoneUpdate) -> tuple[dict, dict | None]:
    """On the university row the route has locked after `can_edit_timeline` (so the select-then-insert cannot race;
    uq_university_milestones_kind is the backstop). Returns the new page and the audit metadata (None when nothing changed). MS7: a moved
    target keeps from / to and whether it was delayed."""
    today = india_today()
    changes = payload.model_dump(include=payload.model_fields_set)
    if changes.get("achieved_on") and changes["achieved_on"] > today:
        raise RequestValidationError([{"type": "value_error", "loc": ("body", "achieved_on"), "msg": ACHIEVED_FUTURE, "input": str(changes["achieved_on"])}])
    rows, derived = await _rows(db, uni.id), await _derived(db, uni.id)
    row = rows.get(kind)
    old = {field: getattr(row, field) if row else None for field in changes}
    changed = sorted(field for field, value in changes.items() if old[field] != value)
    if not changed:
        return _page(rows, derived, today, True), None
    was_delayed = next(i["status"] for i in _items(rows, derived, today) if i["kind"] == kind) == "delayed"
    if row is None:
        row = rows[kind] = UniversityMilestone(university_id=uni.id, kind=kind, updated_by_user_id=user.id)
        db.add(row)
    for field in changed:
        setattr(row, field, changes[field])
    row.updated_by_user_id = user.id
    metadata: dict = {"kind": kind, "fields": changed}
    if "target_date" in changed:
        metadata |= {"target_date": {"from": _iso(old["target_date"]), "to": _iso(changes["target_date"])}, "was_delayed": was_delayed}
    return _page(rows, derived, today, True), metadata
