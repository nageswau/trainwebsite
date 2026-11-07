"""pob-009 (spec docs/superpowers/specs/2026-11-07-pob-009-po-targets-reports-design.md): PO monthly targets (T3), territories (T4), target
company lists (T5), the daily plan (T6) and daily/weekly activity reports (T7) with the contacts drill-down (T8).

T1: a PO (`placement_team`) works on their own records; the Team Lead (`placement_manager`) on their direct reports (`team_filter`; a PO
outside the team is 404, the same as a missing one); super_admin on every PO. Every figure comes from `recruiter_metrics.po_counts`, so a
target sheet, a report and the drill-down agree. Functions only; nothing here commits -- the route owns the transaction."""

import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Company,
    RecruiterActivityReport,
    RecruiterFollowUp,
    RecruiterPlanItem,
    RecruiterProfile,
    RecruiterTarget,
    RecruiterTargetCompany,
    User,
)
from app.schemas import PoTargetItem
from app.services import recruiter_companies as companies
from app.services import recruiter_metrics as metrics
from app.services.bdm_appointments import IST
from app.services.bdm_targets import _percent, edit_refusal, month_status, month_text, shift
from app.services.recruiter import MANAGER_ROLE, ROLE, recruiter_context, require_manager, team_filter

logger = logging.getLogger("app.recruiter")

PO_NOT_FOUND = "Placement officer not found"
INACTIVE = "This placement officer is inactive, so their targets can't be changed"
OWN_ONLY = "You can only view your own activity"
NOT_MONDAY = "A weekly report starts on a Monday"
NOT_STARTED = "This period has not started yet"
FUTURE_PLAN = "You can only plan today"
PAST_PLAN = "Only today's plan can be changed"
ITEM_NOT_FOUND = "Plan item not found"
ALREADY_PLANNED = "This is already in today's plan"
NOT_A_TARGET = "Choose one of this month's target companies"
FOLLOW_UP_CLOSED = "This follow-up is no longer open"
PLAN_CAP = 50  # T6: an abuse bound far above a real day
PLAN_FULL = f"Today's plan already has {PLAN_CAP} items"
ALREADY_SUBMITTED = "This report has already been submitted"
TERRITORY_CAP = 200  # T5
TARGET_COMPANY_NOT_FOUND = "Target company not found"
COMPANY_NOT_FOUND = "Company not found"
KPI_LABELS = {
    "outreach": "Outreach", "responses": "Responses", "meetings": "Meetings", "requirements": "Requirements generated",
    "vendor_registrations": "Vendor registrations", "active_accounts": "Active accounts", "placements": "Placements",
}


def _person(user: User) -> dict:
    return {"id": user.id, "full_name": user.full_name}


def _last_day(month: date) -> date:
    return shift(month, 1) - timedelta(days=1)


# --- T1 who --------------------------------------------------------------------------------------------------------------------------
async def team_member(db: AsyncSession, actor: User, user_id: UUID) -> tuple[User, RecruiterProfile]:
    require_manager(actor)
    row = (await db.execute(select(User, RecruiterProfile).join(RecruiterProfile, RecruiterProfile.user_id == User.id)
                            .where(User.id == user_id, *team_filter(actor)))).first()
    if row is None:
        raise HTTPException(404, PO_NOT_FOUND)
    return row[0], row[1]


async def subject(db: AsyncSession, actor: User, recruiter_id: UUID | None) -> User:
    """The PO whose activity is read: the caller themself (a PO naming another is 403), or a Team Lead's named team member."""
    if actor.role == ROLE:
        await recruiter_context(db, actor)
        if recruiter_id not in (None, actor.id):
            raise HTTPException(403, OWN_ONLY)
        return actor
    if actor.role in (MANAGER_ROLE, "super_admin") and recruiter_id is None:
        raise HTTPException(422, "Choose a placement officer")
    return (await team_member(db, actor, recruiter_id))[0]


def _team_page(actor: User):
    return (select(User, RecruiterProfile).join(RecruiterProfile, RecruiterProfile.user_id == User.id)
            .where(User.active.is_(True), *team_filter(actor)).order_by(User.full_name, User.id))


async def _page(db: AsyncSession, actor: User, limit: int, offset: int) -> tuple[int, list]:
    members = _team_page(actor)
    total = await db.scalar(select(func.count()).select_from(members.order_by(None).subquery()))
    return total or 0, (await db.execute(members.limit(limit).offset(offset))).all()


# --- T3 targets ----------------------------------------------------------------------------------------------------------------------
async def _achieved(db: AsyncSession, ids: list[UUID], month: date, status: str, today: date) -> dict[UUID, dict]:
    """Live actuals for the month to today (none before the month starts)."""
    if status == "future" or not ids:
        return {}
    return await metrics.po_counts(db, ids, month, min(_last_day(month), today))


async def _targets(db: AsyncSession, ids: list[UUID], month: date) -> dict[UUID, dict[str, int]]:
    rows = await db.execute(select(RecruiterTarget.recruiter_user_id, RecruiterTarget.kpi_key, RecruiterTarget.target)
                            .where(RecruiterTarget.recruiter_user_id.in_(ids), RecruiterTarget.month == month))
    out: dict[UUID, dict[str, int]] = defaultdict(dict)
    for user_id, kpi, target in rows:
        out[user_id][kpi] = target
    return out


def _kpis(targets: dict[str, int], counts: dict | None) -> list[dict]:
    rows = []
    for key in metrics.PO_KPIS:
        achieved = counts[key] if counts else None
        rows.append({"key": key, "label": KPI_LABELS[key], "target": targets.get(key), "achieved": achieved, "percent": _percent(targets.get(key), achieved)})
    return rows


async def target_companies(db: AsyncSession, user_id: UUID, month: date) -> list[dict]:
    rows = await db.execute(
        select(RecruiterTargetCompany.id, RecruiterTargetCompany.created_at, Company.id, Company.name, Company.company_code, Company.territory, Company.stage)
        .join(Company, Company.id == RecruiterTargetCompany.company_id)
        .where(RecruiterTargetCompany.recruiter_user_id == user_id, RecruiterTargetCompany.month == month)
        .order_by(Company.name, Company.id)
    )
    return [{"id": tid, "added_at": at, "company": {"id": cid, "name": name, "code": code, "territory": territory, "stage": stage}}
            for tid, at, cid, name, code, territory, stage in rows]


async def sheet(db: AsyncSession, po: User, profile: RecruiterProfile, month: date, current: date, today: date, *, editable: bool) -> dict:
    """One PO's month: each KPI's target, live achieved and percent (AC2), the response rate, the territory and the target companies."""
    status = month_status(month, current)
    counts = (await _achieved(db, [po.id], month, status, today)).get(po.id)
    return {
        "month": month_text(month), "month_status": status, "editable": editable, "recruiter": _person(po), "territory": profile.territory,
        "kpis": _kpis((await _targets(db, [po.id], month)).get(po.id, {}), counts),
        "contacts_reached": counts["contacts_reached"] if counts else None, "response_rate": counts["response_rate"] if counts else None,
        "target_companies": await target_companies(db, po.id, month),
    }


async def team_sheet(db: AsyncSession, actor: User, month: date, current: date, today: date, limit: int, offset: int) -> dict:
    """AC2 for the Team Lead: each active team PO's target vs actual per KPI. Four queries whatever the team size."""
    total, rows = await _page(db, actor, limit, offset)
    ids = [user.id for user, _ in rows]
    status = month_status(month, current)
    targets = await _targets(db, ids, month) if ids else {}
    counts = await _achieved(db, ids, month, status, today)
    items = [{"recruiter": _person(user), "territory": profile.territory, "kpis": _kpis(targets.get(user.id, {}), counts.get(user.id)),
              "response_rate": counts[user.id]["response_rate"] if user.id in counts else None} for user, profile in rows]
    return {"month": month_text(month), "month_status": status, "editable": edit_refusal(actor, month, current) is None,
            "kpis": [{"key": k, "label": KPI_LABELS[k]} for k in metrics.PO_KPIS], "items": items, "total": total, "limit": limit, "offset": offset}


async def _members(db: AsyncSession, actor: User, ids: set[UUID]) -> None:
    rows = (await db.execute(select(User).join(RecruiterProfile, RecruiterProfile.user_id == User.id).where(User.id.in_(ids), *team_filter(actor)))).scalars().all()
    if {u.id for u in rows} != ids:
        raise HTTPException(404, PO_NOT_FOUND)
    if any(not u.active for u in rows):
        raise HTTPException(422, INACTIVE)


async def save_targets(db: AsyncSession, actor: User, month: date, items: list[PoTargetItem]) -> int:
    """T3 (the bdm-016 batch): validate the whole batch, then upsert / clear only what changes; one audit row per PO with from/to."""
    await _members(db, actor, {i.recruiter_user_id for i in items})
    pairs = [(i.recruiter_user_id, i.kpi_key) for i in items]
    existing = await db.execute(
        select(RecruiterTarget.recruiter_user_id, RecruiterTarget.kpi_key, RecruiterTarget.target)
        .where(RecruiterTarget.month == month, tuple_(RecruiterTarget.recruiter_user_id, RecruiterTarget.kpi_key).in_(pairs))
        .with_for_update()
    )
    old = {(user, kpi): target for user, kpi, target in existing.all()}
    changes: dict[UUID, list[dict]] = defaultdict(list)
    for item in items:
        key = (item.recruiter_user_id, item.kpi_key)
        if old.get(key) == item.target:
            continue
        changes[item.recruiter_user_id].append({"kpi": item.kpi_key, "from": old.get(key), "to": item.target})
        old[key] = item.target  # a repeated pair in one batch: the last value wins and is audited once per change
        if item.target is None:
            await db.execute(delete(RecruiterTarget).where(RecruiterTarget.recruiter_user_id == item.recruiter_user_id, RecruiterTarget.month == month,
                                                           RecruiterTarget.kpi_key == item.kpi_key))
            continue
        values = {"target": item.target, "set_by_user_id": actor.id, "set_at": func.now(), "updated_at": func.now()}
        await db.execute(insert(RecruiterTarget).values(recruiter_user_id=item.recruiter_user_id, month=month, kpi_key=item.kpi_key, **values)
                         .on_conflict_do_update(constraint="uq_recruiter_targets_user_month_kpi", set_=values))
    for user_id, changed in changes.items():
        audit(db, actor, "recruiter_target.set", "recruiter_targets", user_id, {"month": month_text(month), "changes": changed})
    return sum(len(c) for c in changes.values())


# --- T4 territory, T5 target companies -----------------------------------------------------------------------------------------------
async def set_territory(db: AsyncSession, actor: User, user_id: UUID, territory: str | None) -> dict:
    po, profile = await team_member(db, actor, user_id)
    before = profile.territory
    if before != territory:
        profile.territory = territory
        audit(db, actor, "recruiter_territory.set", "recruiter_profiles", po.id, {"from": before, "to": territory})
    return {"recruiter": _person(po), "territory": territory}


def _target_company_filter():
    return [Company.archived_at.is_(None), Company.merged_into_id.is_(None), companies.CLIENT_COMPANY]


async def add_target_companies(db: AsyncSession, actor: User, user_id: UUID, month: date, company_ids: list[UUID] | None, territory: str | None) -> int:
    """T5: every named company must be an active client company in the Team Lead's company scope (404 otherwise); by territory, every such
    company with that territory (case-insensitive), at most 200. A company already on the list is skipped. Ownership is untouched."""
    po, _ = await team_member(db, actor, user_id)
    if not po.active:
        raise HTTPException(422, INACTIVE)
    scope = [*await companies.caller_scope(db, actor), *_target_company_filter()]
    if company_ids is not None:
        wanted = set(company_ids)
        found = set((await db.scalars(select(Company.id).where(Company.id.in_(wanted), *scope))).all())
        if found != wanted:
            raise HTTPException(404, COMPANY_NOT_FOUND)
    else:
        found = set((await db.scalars(select(Company.id).where(func.lower(Company.territory) == territory.lower(), *scope)
                                      .order_by(Company.name).limit(TERRITORY_CAP))).all())
    if not found:
        return 0
    inserted = await db.execute(
        insert(RecruiterTargetCompany).values([{"recruiter_user_id": po.id, "company_id": cid, "month": month, "added_by_user_id": actor.id} for cid in found])
        .on_conflict_do_nothing(constraint="uq_recruiter_target_companies").returning(RecruiterTargetCompany.company_id)
    )
    added = sorted(str(cid) for cid in inserted.scalars().all())
    if added:
        audit(db, actor, "recruiter_target_company.added", "recruiter_target_companies", po.id,
              {"month": month_text(month), "territory": territory, "company_ids": added})
    return len(added)


async def remove_target_company(db: AsyncSession, actor: User, row_id: UUID) -> None:
    require_manager(actor)
    row = await db.scalar(select(RecruiterTargetCompany).where(
        RecruiterTargetCompany.id == row_id,
        RecruiterTargetCompany.recruiter_user_id.in_(select(RecruiterProfile.user_id).where(*team_filter(actor))),
    ).with_for_update())
    if row is None:
        raise HTTPException(404, TARGET_COMPANY_NOT_FOUND)
    await db.delete(row)
    audit(db, actor, "recruiter_target_company.removed", "recruiter_target_companies", row.recruiter_user_id,
          {"month": month_text(row.month), "company_id": str(row.company_id)})


# --- T6 the daily plan ---------------------------------------------------------------------------------------------------------------
def _end_of(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=IST)


def _follow_up_out(fu: RecruiterFollowUp, company: Company) -> dict:
    return {"id": fu.id, "reason": fu.reason, "due_at": fu.due_at, "status": fu.status, "priority": fu.priority, "notes": fu.notes,
            "company": {"id": company.id, "name": company.name}}


async def plan(db: AsyncSession, po: User, day: date, today: date) -> dict:
    """The PO's plan for `day` and, for today, what is left to pick: open follow-ups due by the end of today on their companies, and this
    month's target companies (T6)."""
    if day > today:
        raise HTTPException(422, FUTURE_PLAN)
    rows = await db.execute(
        select(RecruiterPlanItem, RecruiterFollowUp, Company)
        .outerjoin(RecruiterFollowUp, RecruiterFollowUp.id == RecruiterPlanItem.follow_up_id)
        .join(Company, Company.id == func.coalesce(RecruiterPlanItem.company_id, RecruiterFollowUp.company_id))
        .where(RecruiterPlanItem.recruiter_user_id == po.id, RecruiterPlanItem.plan_date == day)
        .order_by(RecruiterPlanItem.created_at, RecruiterPlanItem.id)
    )
    items = [{"id": item.id, "kind": "follow_up" if fu else "company", "done_at": item.done_at,
              "follow_up": _follow_up_out(fu, company) if fu else None, "company": {"id": company.id, "name": company.name}}
             for item, fu, company in rows]
    out = {"date": day, "editable": day == today, "items": items, "suggested_follow_ups": [], "suggested_companies": []}
    if day != today:
        return out
    planned_fus = {i["follow_up"]["id"] for i in items if i["follow_up"]}
    planned_cos = {i["company"]["id"] for i in items if i["kind"] == "company"}
    due = await db.execute(
        select(RecruiterFollowUp, Company).join(Company, Company.id == RecruiterFollowUp.company_id)
        .where(RecruiterFollowUp.status == "open", RecruiterFollowUp.due_at < _end_of(today), Company.assigned_recruiter_user_id == po.id,
               Company.archived_at.is_(None))
        .order_by(RecruiterFollowUp.due_at, RecruiterFollowUp.id).limit(PLAN_CAP)
    )
    out["suggested_follow_ups"] = [{"follow_up": _follow_up_out(fu, company)} for fu, company in due if fu.id not in planned_fus]
    out["suggested_companies"] = [row["company"] for row in await target_companies(db, po.id, today.replace(day=1)) if row["company"]["id"] not in planned_cos]
    return out


async def lock_plan(db: AsyncSession, po: User, day: date) -> None:
    """Serialises one PO's plan writes (the cap and the duplicate check) on their profile row."""
    await db.execute(select(RecruiterProfile.id).where(RecruiterProfile.user_id == po.id).with_for_update())


async def add_plan_item(db: AsyncSession, po: User, today: date, follow_up_id: UUID | None, company_id: UUID | None) -> RecruiterPlanItem:
    if follow_up_id is not None:
        fu = await db.scalar(select(RecruiterFollowUp).join(Company, Company.id == RecruiterFollowUp.company_id)
                             .where(RecruiterFollowUp.id == follow_up_id, Company.assigned_recruiter_user_id == po.id))
        if fu is None:
            raise HTTPException(404, "Follow-up not found")
        if fu.status != "open":
            raise HTTPException(422, FOLLOW_UP_CLOSED)
        taken = RecruiterPlanItem.follow_up_id == follow_up_id
    else:
        on_list = await db.scalar(select(RecruiterTargetCompany.id).where(RecruiterTargetCompany.recruiter_user_id == po.id,
                                                                          RecruiterTargetCompany.month == today.replace(day=1), RecruiterTargetCompany.company_id == company_id))
        if on_list is None:
            raise HTTPException(422, NOT_A_TARGET)
        taken = RecruiterPlanItem.company_id == company_id
    mine = and_(RecruiterPlanItem.recruiter_user_id == po.id, RecruiterPlanItem.plan_date == today)
    if await db.scalar(select(RecruiterPlanItem.id).where(mine, taken)):
        raise HTTPException(409, ALREADY_PLANNED)
    if (await db.scalar(select(func.count()).select_from(RecruiterPlanItem).where(mine))) >= PLAN_CAP:
        raise HTTPException(422, PLAN_FULL)
    item = RecruiterPlanItem(recruiter_user_id=po.id, plan_date=today, follow_up_id=follow_up_id, company_id=company_id)
    db.add(item)
    return item


async def own_plan_item(db: AsyncSession, po: User, item_id: UUID, today: date) -> RecruiterPlanItem:
    item = await db.scalar(select(RecruiterPlanItem).where(RecruiterPlanItem.id == item_id, RecruiterPlanItem.recruiter_user_id == po.id).with_for_update())
    if item is None:
        raise HTTPException(404, ITEM_NOT_FOUND)
    if item.plan_date != today:
        raise HTTPException(422, PAST_PLAN)
    return item


def plan_item_out(item: RecruiterPlanItem) -> dict:
    return {"id": item.id, "plan_date": item.plan_date, "follow_up_id": item.follow_up_id, "company_id": item.company_id, "done_at": item.done_at}


# --- T7 activity reports -------------------------------------------------------------------------------------------------------------
def period_dates(period: str, start: date, today: date) -> tuple[date, date]:
    """T7: a day, or a Monday-Sunday IST week; a period that has not started is 422."""
    if period == "weekly" and start.weekday() != 0:
        raise HTTPException(422, NOT_MONDAY)
    if start > today:
        raise HTTPException(422, NOT_STARTED)
    return start, start + timedelta(days=6 if period == "weekly" else 0)


async def live_counts(db: AsyncSession, po: User, period: str, first: date, last: date, today: date) -> dict:
    counts = (await metrics.po_counts(db, [po.id], first, min(last, today)))[po.id]
    if period == "daily":
        planned, done = (await db.execute(select(func.count(), func.count(RecruiterPlanItem.done_at))
                                          .where(RecruiterPlanItem.recruiter_user_id == po.id, RecruiterPlanItem.plan_date == first))).one()
        counts = counts | {"plan": {"planned": planned, "done": done}}
    return counts


async def submitted(db: AsyncSession, po_id: UUID, period: str, start: date) -> RecruiterActivityReport | None:
    return await db.scalar(select(RecruiterActivityReport).where(RecruiterActivityReport.recruiter_user_id == po_id,
                                                                 RecruiterActivityReport.period == period, RecruiterActivityReport.period_start == start))


async def report_out(db: AsyncSession, po: User, period: str, start: date, today: date, report: RecruiterActivityReport | None) -> dict:
    first, last = period_dates(period, start, today)
    counts = dict(report.counts) if report else await live_counts(db, po, period, first, last, today)
    plan_counts = counts.pop("plan", None)
    return {"recruiter": _person(po), "period": period, "period_start": first, "period_end": last, "status": "submitted" if report else "draft",
            "counts": counts, "plan": plan_counts, "note": report.note if report else None, "submitted_at": report.submitted_at if report else None,
            "kpis": [{"key": k, "label": KPI_LABELS[k]} for k in metrics.PO_KPIS]}


async def team_reports(db: AsyncSession, actor: User, period: str, start: date, today: date, limit: int, offset: int) -> dict:
    """The Team Lead's grid: each active team PO's report for the period -- submitted (with its headline figures) or missing."""
    require_manager(actor)
    first, last = period_dates(period, start, today)
    total, rows = await _page(db, actor, limit, offset)
    found = {}
    if rows:
        reports = await db.scalars(select(RecruiterActivityReport).where(RecruiterActivityReport.recruiter_user_id.in_([u.id for u, _ in rows]),
                                                                         RecruiterActivityReport.period == period, RecruiterActivityReport.period_start == first))
        found = {r.recruiter_user_id: r for r in reports}

    def row(user: User) -> dict:
        report = found.get(user.id)
        counts = report.counts if report else {}
        return {"recruiter": _person(user), "status": "submitted" if report else "missing", "submitted_at": report.submitted_at if report else None,
                "outreach": counts.get("outreach"), "response_rate": counts.get("response_rate"), "meetings": counts.get("meetings")}

    return {"period": period, "period_start": first, "period_end": last, "items": [row(u) for u, _ in rows], "total": total, "limit": limit, "offset": offset}


# --- shared ----------------------------------------------------------------------------------------------------------------------------
def audit(db: AsyncSession, actor: User, action: str, entity_type: str, entity_id, metadata: dict) -> None:
    """Same transaction as the write (fail closed); ids, keys and numbers only."""
    db.add(AuditLog(user_id=actor.id, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata))


def log(event: str, actor: User, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(actor.id), **{k: str(v) for k, v in extra.items()}}})

