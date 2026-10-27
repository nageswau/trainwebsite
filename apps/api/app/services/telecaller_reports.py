"""tel-024 (DEC-SCOPE-109, spec docs/superpowers/specs/2026-10-07-tel-024-management-reports-design.md): the five EVID-019 §21
management reports. Reads only; aggregates only (no lead name, mobile or email ever leaves here, so Q-20 masking does not arise).

The cohort reports (source, product, campaign, handover) count leads CREATED in the range, in the caller's scope -- the same scope as
the Leads list they open from, so a total reconciles with it (AC1). A lead's reached index is the highest pipeline position among its
current stage and every stage in its history (closed outcomes have none): it counts in every column up to it, so a funnel is monotonic
(DEC-SCOPE-036 D3). Enrolled is a lead still converted now (RP2, tel-021 DB2). The telecaller report is activity in the range (RP1):
`telecaller_metrics.flow_counts_by_user`, the dashboard's own counts.

nehn-013 (DEC-SCOPE-299, spec docs/superpowers/specs/2026-10-27-nehn-013-crm-report-gaps-design.md) appends Lost (current loss stage, R1)
and Conversion rate (enrolled / leads, R2) to the funnel reports and adds the counselor (by owner, R5) and date-wise (IST day / week /
month of creation, R6) cohorts, plus two follow-up reports on the telecaller-side follow-ups DUE in the range (R7, R8). The pending
follow-up list is the one report that names a lead (R8: a manager cannot act on it otherwise) -- never its mobile or email."""

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy import case, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import LOSS_STAGES, ORDER, label
from app.models import Enquiry, LeadFollowUp, LeadLostReason, LeadStageHistory, TelCampaign, TelecallerProfile, TelProduct, User
from app.services import lead_pipeline, telecaller_metrics
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import IST, db_now, today_ist
from app.services.telecaller import TEAMS
from app.tel_sources import TEL_SOURCES

DIVISION_ADMINS = frozenset({"it_admin", "overseas_admin"})
MAX_DAYS = 366
SOURCE_LABELS = {
    "instagram": "Instagram", "facebook": "Facebook", "google": "Google", "website": "Website", "whatsapp": "WhatsApp", "walk_in": "Walk-in",
    "college": "College", "school": "School", "agent": "Agent", "referral": "Referral", "exhibition_event": "Exhibition/Event", "bdm": "BDM",
    "other": "Other",
}
RANK = {stage: index for index, stage in enumerate(ORDER)}
LOST, RATE = ("lost", "Lost", "lost"), ("conversion_rate", "Conversion rate (%)", None)  # nehn-013 R1, R2: appended, never reordered
FUNNEL = (("leads", "Leads", None), ("connected", "Connected", "contacted"), ("qualified", "Qualified", "qualified"),
          ("counselling", "Counselling", "counselling_scheduled"), ("enrolled", "Enrolled", "converted"), LOST, RATE)
COUNSELOR = (("leads", "Leads", None), ("counselling_done", "Counselling done", "counselling_completed"), ("enrolled", "Enrolled", "converted"),
             LOST, RATE)
FOLLOW_UPS = (("follow_ups", "Follow-ups", None), ("completed", "Completed", "done"), ("open", "Open", "open"), ("overdue", "Overdue", "overdue"),
              ("cancelled", "Cancelled", "cancelled"))
GROUPS = ("day", "week", "month")
# The EVID-019 §7 reason labels, as the web client's lib/telecallerFollowUps.ts (a test pins the keys to LEAD_FOLLOW_UP_REASONS).
FOLLOW_UP_REASONS = {
    "discuss_with_parents": "Need to discuss with parents", "course_details": "Need course details", "fee_details": "Need fee details",
    "waiting_salary": "Waiting for salary", "waiting_documents": "Waiting for documents", "comparing_courses": "Comparing courses",
    "next_month": "Interested next month", "next_intake": "Interested next intake",
    "university_information": "Waiting for university information", "counselor_call": "Requested counselor call",
}
HANDOVER = (("handed_over", "Handed over", None), ("counselling_done", "Counselling done", "counselling_completed"), ("enrolled", "Enrolled", "converted"))
LOSSES = (("leads", "Leads", None), *((stage, label(stage), stage) for stage in LOSS_STAGES))
NO_REASON = "No reason recorded"  # D6: a call-logged close, or a lead closed before ccrm-006
ACTIVITY = (("calls", "Calls", "calls"), ("connected", "Connected", "connected_calls"), ("qualified", "Qualified", "qualified_leads"),
            ("appointments", "Appointments", "new_appointments"), ("conversions", "Conversions", "converted_leads"))


@dataclass(frozen=True)
class Report:
    title: str
    labels: tuple[tuple[str, str], ...]  # the row's name columns: (key, header)
    counts: tuple[tuple[str, str, str | None], ...]  # (key, header, stage reached / source count)
    ordered: bool = False  # the rows keep the query's order (calendar order) instead of most-first


REPORTS = {
    "source": Report("Lead Source Report", (("label", "Source"),), FUNNEL),
    "product": Report("Course Report", (("label", "Course"),), FUNNEL),
    "telecaller": Report("Telecaller Report", (("telecaller", "Telecaller"),), ACTIVITY),
    "handover": Report("Counselor Handover Report", (("telecaller", "Telecaller"), ("counselor", "Counselor")), HANDOVER),
    "campaign": Report("Campaign Report", (("label", "Campaign"),), FUNNEL),
    # ccrm-006 (DEC-SCOPE-264, D9): the cohort's leads now Lost / Not Interested, by reason -- counted by current stage, not reach
    "lost": Report("Lost Reasons Report", (("label", "Reason"),), LOSSES),
    # nehn-013 (DEC-SCOPE-299)
    "counselor": Report("Counselor Report", (("counselor", "Counselor"),), COUNSELOR),
    "date": Report("Date-wise Report", (("period", "Period"),), FUNNEL, ordered=True),
    "follow_ups": Report("Follow-up Status Report", (("telecaller", "Telecaller"),), FOLLOW_UPS),
    "pending_follow_ups": Report("Pending Follow-ups Report", (("lead", "Lead"), ("telecaller", "Telecaller"), ("due", "Due date"), ("reason", "Reason")),
                                 (("overdue_days", "Days overdue", None),)),
}
UNSUMMED = frozenset({"conversion_rate", "overdue_days"})  # a Total row recomputes a rate and leaves days overdue blank
LEAD_FILTERS = ("product_id", "campaign_id", "source")  # cohort reports only; the telecaller report is per actor, not per lead


class ReportInputError(Exception):
    """A refused input; the message names the form's field, as the page shows it (the 422 detail)."""


@dataclass(frozen=True)
class Filters:
    date_from: date
    date_to: date
    team: str | None = None
    product_id: UUID | None = None
    campaign_id: UUID | None = None
    source: str | None = None
    group: str = "day"  # the date-wise report's period (R6)
    given: tuple[str, ...] = field(default=())  # which filters the caller set (the audit names them, never their values)


def _date(raw: str | None, label: str, default: date) -> date:
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ReportInputError(f"'{label}' is not a valid date") from None


def _uuid(raw: str | None, what: str) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        raise ReportInputError(f"Choose a {what} from the list") from None


def parse_filters(raw: dict[str, str | None], today: date) -> Filters:
    """Defaults: the 1st of the current IST month to today. A range is at most 366 days (bounded queries, backlog performance note)."""
    start = _date(raw.get("date_from"), "From", today.replace(day=1))
    end = _date(raw.get("date_to"), "To", today)
    if start > end:
        raise ReportInputError("'From' must be on or before 'To'")
    if (end - start).days >= MAX_DAYS:
        raise ReportInputError(f"Choose a range of at most {MAX_DAYS} days")
    team, source = raw.get("team") or None, raw.get("source") or None
    if team is not None and team not in TEAMS:
        raise ReportInputError("Choose a team from the list")
    if source is not None and source not in TEL_SOURCES:
        raise ReportInputError("Choose a source from the list")
    group = raw.get("group") or "day"
    if group not in GROUPS:
        raise ReportInputError("Choose day, week or month")
    product_id, campaign_id = _uuid(raw.get("product_id"), "course"), _uuid(raw.get("campaign_id"), "campaign")
    given = tuple(k for k in ("date_from", "date_to", "team", *LEAD_FILTERS, "group") if raw.get(k))
    return Filters(start, end, team, product_id, campaign_id, source, group, given)


# --- scope (T24, RBAC §2.35) -------------------------------------------------------------------------------------------------------

def lead_scope(user: User) -> list:
    """Exactly the Leads list the caller works from: a manager's `/telecaller/leads` scope, a division admin's `/admin/leads` division."""
    if user.role in DIVISION_ADMINS:
        return [Enquiry.division == user.division]
    return lead_pipeline.scope(user)[1]


def _telecaller_scope(user: User) -> list:
    if user.role in DIVISION_ADMINS:
        return [TelecallerProfile.team == user.division]
    return [] if user.role == "super_admin" else [TelecallerProfile.reporting_manager_user_id == user.id]


async def _teams(db: AsyncSession, user: User) -> list[str]:
    """The teams the caller reports on: an admin's division, a manager's reports' teams, every team for super_admin."""
    if user.role in DIVISION_ADMINS:
        return [user.division]
    if user.role == "super_admin":
        return list(TEAMS)
    return sorted(set(await db.scalars(select(TelecallerProfile.team).where(TelecallerProfile.reporting_manager_user_id == user.id))))


async def options(db: AsyncSession, user: User) -> dict:
    """The filter pickers: products and campaigns of the caller's teams, inactive ones too (old leads keep them)."""
    teams = await _teams(db, user)
    in_teams = or_(TelProduct.team.in_(teams), TelProduct.team.is_(None))  # an Other product with no team routes to the queue
    products = (await db.execute(select(TelProduct.id, TelProduct.name).where(in_teams).order_by(TelProduct.name))).all()
    campaigns = (await db.execute(
        select(TelCampaign.id, TelCampaign.name).join(TelProduct, TelProduct.id == TelCampaign.product_id).where(in_teams).order_by(TelCampaign.name)
    )).all()
    return {
        "teams": teams,
        "sources": [{"key": key, "label": SOURCE_LABELS[key]} for key in TEL_SOURCES],
        "products": [{"id": str(i), "name": n} for i, n in products],
        "campaigns": [{"id": str(i), "name": n} for i, n in campaigns],
    }


# --- the reports ------------------------------------------------------------------------------------------------------------------

def _rank(column):
    return case(RANK, value=column, else_=-1)


def _reached():
    """The highest pipeline position the lead has reached: its current stage or any stage in its history."""
    history = select(func.max(_rank(LeadStageHistory.to_stage))).where(LeadStageHistory.lead_id == Enquiry.id).scalar_subquery()
    return func.greatest(_rank(Enquiry.status), func.coalesce(history, -1))


def _count(stage: str | None):
    if stage is None:
        return func.count()
    if stage == "converted":  # RP2: still converted now, not merely reached once
        return func.count().filter(Enquiry.status == "converted")
    if stage == "lost":  # nehn-013 R1: lost now -- a reopened lead is not
        return func.count().filter(Enquiry.status.in_(LOSS_STAGES))
    return func.count().filter(_reached() >= RANK[stage])


def _lead_filters(user: User, f: Filters, anchor=Enquiry.created_at) -> list:
    """The caller's leads matching the filters, `anchor` (creation; a follow-up's due time) inside the range."""
    start, end = day_range(f.date_from)[0], day_range(f.date_to)[1]
    where = [*lead_scope(user), anchor >= start, anchor < end]
    for column, value in ((Enquiry.division, f.team), (Enquiry.product_id, f.product_id), (Enquiry.campaign_id, f.campaign_id), (Enquiry.source, f.source)):
        if value is not None:
            where.append(column == value)
    return where


async def _names(db: AsyncSession, model, ids: set, column) -> dict:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return dict((await db.execute(select(model.id, column).where(model.id.in_(ids)))).all())


async def _cohort(db: AsyncSession, user: User, kind: str, spec: Report, f: Filters) -> list[dict]:
    # R6: the IST calendar period. Literals, not bind parameters, so the SELECT and GROUP BY expressions are identical to PostgreSQL;
    # `group` is one of GROUPS (parse_filters), so it is never caller text.
    period = func.date_trunc(literal_column(f"'{f.group}'"), func.timezone(literal_column(f"'{IST.key}'"), Enquiry.created_at))
    by_kind: dict[str, list] = {"source": [Enquiry.source], "product": [Enquiry.product_id], "campaign": [Enquiry.campaign_id],
                                "handover": [Enquiry.telecaller_user_id, Enquiry.owner_id], "lost": [Enquiry.lost_reason_id],
                                "counselor": [Enquiry.owner_id], "date": [period]}
    keys = by_kind[kind]
    owned = [Enquiry.owner_id.is_not(None)]
    where = _lead_filters(user, f) + {"handover": owned, "counselor": owned, "lost": [Enquiry.status.in_(LOSS_STAGES)]}.get(kind, [])
    if kind == "lost":
        counts = [(func.count() if stage is None else func.count().filter(Enquiry.status == stage)).label(key) for key, _, stage in spec.counts]
    else:
        counts = [_count(stage).label(key) for key, _, stage in spec.counts if key not in UNSUMMED]
    rows = (await db.execute(select(*keys, *counts).where(*where).group_by(*keys).order_by(*keys))).all()
    if kind == "date":
        return [{"period": _period(r[0], f.group)} | dict(r._mapping) for r in rows]
    if kind == "counselor":
        people = await _names(db, User, {r[0] for r in rows}, User.full_name)
        return [{"counselor": people.get(r[0], "")} | dict(r._mapping) for r in rows]
    if kind == "lost":
        names = await _names(db, LeadLostReason, {r[0] for r in rows}, LeadLostReason.name)
        return [{"label": names.get(r[0], NO_REASON)} | dict(r._mapping) for r in rows]
    if kind == "source":
        return [{"label": SOURCE_LABELS.get(r[0], r[0])} | dict(r._mapping) for r in rows]
    if kind == "handover":
        people = await _names(db, User, {r[0] for r in rows} | {r[1] for r in rows}, User.full_name)
        return [{"telecaller": people.get(r[0], "Unassigned"), "counselor": people.get(r[1], "")} | dict(r._mapping) for r in rows]
    model, none = (TelProduct, "No product") if kind == "product" else (TelCampaign, "No campaign")
    names = await _names(db, model, {r[0] for r in rows}, model.name)
    return [{"label": names.get(r[0], none)} | dict(r._mapping) for r in rows]


def _period(start, group: str) -> str:
    """A period's row label: its first IST day; a week starts on Monday (PostgreSQL date_trunc)."""
    return {"day": start.date().isoformat(), "week": f"Week of {start.date().isoformat()}", "month": start.strftime("%B %Y")}[group]


async def _follow_ups(db: AsyncSession, user: User, kind: str, f: Filters) -> list[dict]:
    """R7 / R8: the telecaller-side follow-ups (the dashboard's TELECALLER_FOLLOW_UP) on the caller's leads, due in the range."""
    now = await db_now(db)
    where = [*_lead_filters(user, f, LeadFollowUp.due_at), lead_pipeline.TELECALLER_FOLLOW_UP]
    base = select().select_from(LeadFollowUp).join(Enquiry, Enquiry.id == LeadFollowUp.lead_id)
    if kind == "follow_ups":
        overdue = (LeadFollowUp.status == "open") & (LeadFollowUp.due_at < now)
        counts = [func.count().label(key) if state is None else
                  func.count().filter(overdue if state == "overdue" else LeadFollowUp.status == state).label(key) for key, _, state in FOLLOW_UPS]
        rows = (await db.execute(base.add_columns(Enquiry.telecaller_user_id, *counts).where(*where).group_by(Enquiry.telecaller_user_id))).all()
        people = await _names(db, User, {r[0] for r in rows}, User.full_name)
        return [{"telecaller": people.get(r[0], "Unassigned")} | dict(r._mapping) for r in rows]
    rows = (await db.execute(base.add_columns(Enquiry.name, Enquiry.telecaller_user_id, LeadFollowUp.due_at, LeadFollowUp.reason).where(
        *where, LeadFollowUp.status == "open", LeadFollowUp.due_at < now))).all()
    people, today = await _names(db, User, {r[1] for r in rows}, User.full_name), today_ist(now)
    return [{"lead": name, "telecaller": people.get(tel, "Unassigned"), "due": due.astimezone(IST).date().isoformat(),
             "reason": FOLLOW_UP_REASONS.get(reason, reason), "overdue_days": (today - due.astimezone(IST).date()).days}
            for name, tel, due, reason in rows]


def _rate(row: dict) -> float:
    return round(row["enrolled"] * 100 / row["leads"], 1) if row["leads"] else 0.0


async def _telecallers(db: AsyncSession, user: User, f: Filters) -> list[dict]:
    where = _telecaller_scope(user) + ([TelecallerProfile.team == f.team] if f.team else [])
    people = (await db.execute(
        select(User.id, User.full_name, User.active).join(TelecallerProfile, TelecallerProfile.user_id == User.id).where(User.role == "telecaller", *where)
    )).all()
    counts = await telecaller_metrics.flow_counts_by_user(db, [p.id for p in people], day_range(f.date_from)[0], day_range(f.date_to)[1])
    return [{"telecaller": name if active else f"{name} (inactive)"} | {key: counts[i][source] for key, _, source in ACTIVITY}
            for i, name, active in people]


async def report(db: AsyncSession, user: User, kind: str, f: Filters) -> dict:
    """One report: its columns, rows (most first, then by name) and a Total row."""
    spec = REPORTS[kind]
    if kind == "telecaller":
        rows = await _telecallers(db, user, f)
    elif kind in ("follow_ups", "pending_follow_ups"):
        rows = await _follow_ups(db, user, kind, f)
    else:
        rows = await _cohort(db, user, kind, spec, f)
    labels = [key for key, _ in spec.labels]
    count_keys = [key for key, _, _ in spec.counts]
    items = [{k: r[k] for k in (*labels, *count_keys) if k in r} for r in rows]
    if not spec.ordered:
        items.sort(key=lambda r: (-r[count_keys[0]], *(str(r[k]).lower() for k in labels)))
    # QA-04: a list with nothing to sum (pending follow-ups) counts its rows instead
    first = f"Total ({len(items)})" if all(k in UNSUMMED for k in count_keys) else "Total"
    totals = {labels[0]: first, **{k: "" for k in labels[1:]}, **{k: "" if k in UNSUMMED else sum(r[k] for r in items) for k in count_keys}}
    if "conversion_rate" in count_keys:  # R2: each row's own rate; the Total row's from the totals, never a sum of rates
        for line in (*items, totals):
            line["conversion_rate"] = _rate(line)
    return {
        "kind": kind, "title": spec.title, "date_from": f.date_from, "date_to": f.date_to,
        "columns": [{"key": k, "label": h} for k, h in spec.labels] + [{"key": k, "label": h} for k, h, _ in spec.counts],
        "items": items, "totals": totals, "options": await options(db, user),
    }
