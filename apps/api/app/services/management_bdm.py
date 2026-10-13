"""mgmt-020 (EVID-017 §16, spec BD1-BD12): the BDM dashboards -- one figure set per BDM type, company-wide, for an IST period.

Nothing is computed here that bdm-024 or bdm-015/016 do not already define. The bdm-024 figures (P-01/P-02/P-04/P-05/P-07 and the
master view's agent chain) run bdm-024's own functions over every BDM of the type, so they equal its "All BDM teams" totals (AC); the
rest are the bdm-015/016 builders over the same BDMs, plus two agency-link counts (BD8/BD9). Read-only; only counts leave."""

from datetime import date, datetime

from sqlalchemy import ScalarSelect, Select, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrg, BdmOnboardingRequest, BdmOrganization, BdmProfile
from app.services.bdm_metrics import DAILY_METRICS, TARGET_METRICS
from app.services.bdm_performance import _instants, figures, hierarchy, team_members, total

LABELS = {"agent": "Agent BDM", "school": "School BDM", "college": "College BDM"}


def _new_agents(bdm: Select, start: datetime, end: datetime) -> ScalarSelect:
    """BD8: the BDMs' Agent organizations linked to an agency (onboarding completed, bdm-019) in the window."""
    return select(func.count(distinct(BdmOnboardingRequest.organization_id))).join(
        BdmOrganization, BdmOrganization.id == BdmOnboardingRequest.organization_id
    ).where(BdmOrganization.assigned_bdm_user_id.in_(bdm), BdmOnboardingRequest.kind == "agent", BdmOnboardingRequest.status == "completed",
            BdmOnboardingRequest.resolved_at >= start, BdmOnboardingRequest.resolved_at < end).scalar_subquery()  # fmt: skip


def _active_agents(bdm: Select, _start: datetime, _end: datetime) -> ScalarSelect:
    """BD9: the BDMs' non-archived Agent organizations whose linked agency is active now."""
    return (
        select(func.count())
        .select_from(BdmOrganization)
        .join(AgentOrg, AgentOrg.id == BdmOrganization.agent_org_id)
        .where(BdmOrganization.assigned_bdm_user_id.in_(bdm), BdmOrganization.archived_at.is_(None), AgentOrg.status == "active")
        .scalar_subquery()
    )


# Where a figure comes from: ("performance", bdm-024 figure) | ("master", bdm-024 agent chain step) | a builder(bdm, start, end) | None.
PROSPECTS = ("performance", "new_organizations")
MEETINGS = ("Meetings", "Appointments the {who} completed in the period.", "period", ("performance", "meetings"))
VISITS = ("Visits", "Visits the {who} logged in the period.", "period", DAILY_METRICS["school_visits"][1])
SIGNED = ("MoUs the {who} moved to Signed in the period.", "period", ("performance", "mous"))

# BD4-BD11: type -> ((key, label, definition, basis, source), ...) in §16 order. `{who}` is "Agent BDMs", "School BDMs" or "College BDMs".
FIGURES: dict[str, tuple[tuple[str, str, str, str, object], ...]] = {
    "agent": (
        ("agent_prospects", "Agent prospects", "Organizations the {who} created in the period.", "period", PROSPECTS),
        ("meetings", *MEETINGS),
        ("visits", *VISITS),
        ("agreements", "Agreements", *SIGNED),
        ("new_agents", "New agents", "Organizations of the {who} linked to an agency (onboarding completed) in the period.", "period", _new_agents),
        ("active_agents", "Active agents", "Organizations of the {who} linked to an agency that is active now.", "now", _active_agents),
        ("agent_students", "Agent students", "Active students added in the period in the agencies linked to the {who}' organizations.", "period",
         ("performance", "students")),
        ("applications", "Applications", "The linked agencies' applications, except withdrawn ones (all time).", "now", ("master", "applications")),
        ("enrollments", "Enrollments", "The linked agencies' applications at the Enrolled stage (all time).", "now", ("master", "enrollment")),
    ),
    "school": (
        ("school_leads", "School leads", "Organizations the {who} created in the period.", "period", PROSPECTS),
        ("meetings", *MEETINGS),
        ("visits", *VISITS),
        ("proposals", "Proposals", "MoUs the {who} moved to Proposal Sent in the period.", "period", TARGET_METRICS["proposals"][2]),
        ("mous", "MoUs", *SIGNED),
        ("active_schools", "Active schools", "Schools linked to the {who}' organizations with a tier still valid at the period's end (today while it runs).",
         "period", TARGET_METRICS["active_schools"][2]),
        ("students", "Students", "Students added in the period in the schools linked to the {who}' organizations.", "period", ("performance", "students")),
    ),
    "college": (
        ("college_prospects", "College prospects", "Organizations the {who} created in the period.", "period", PROSPECTS),
        ("meetings", *MEETINGS),
        ("mous", "MoUs", *SIGNED),
        ("course_promotions", "Course promotions", "Course promotion appointments the {who} completed in the period.", "period",
         TARGET_METRICS["course_promotions"][2]),
        ("internships", "Internships", "Not tracked: internships are not recorded in EduSphere.", "period", None),
        ("student_registrations", "Student registrations", "Students whose lead from the {who}' organizations was converted in the period.", "period",
         ("performance", "students")),
    ),
}  # fmt: skip


async def dashboard(db: AsyncSession, bdm_type: str, start: date, end: date, now: datetime) -> dict:
    """The type's figures for the inclusive IST dates `start`..`end`. Every BDM of the type, active or not (BD1)."""
    team = select(BdmProfile.user_id).where(BdmProfile.bdm_type == bdm_type)
    rows = FIGURES[bdm_type]
    sources = [source for *_, source in rows]
    members = await team_members(db, team)
    performance = total((await figures(db, team, start, end)).values(), bdm_type)
    master: dict = {}
    if any(isinstance(s, tuple) and s[0] == "master" for s in sources):
        chain = next(t for t in await hierarchy(db, team) if t["type"] == bdm_type)
        master = {step["key"]: value for step, value in zip(chain["chain"], chain["totals"], strict=True)}
    lo, hi = _instants(start, end)
    built = {key: source(team, lo, hi) for key, *_, source in rows if callable(source)}
    counted = dict(zip(built, (await db.execute(select(*built.values()))).one(), strict=True)) if built else {}

    def value(key: str, source):
        if isinstance(source, tuple):
            return (performance if source[0] == "performance" else master)[source[1]]
        return counted.get(key)

    who = f"{bdm_type.capitalize()} BDMs"
    return {
        "type": bdm_type,
        "label": LABELS[bdm_type],
        "from_": start,
        "to": end,
        "as_of": now,
        "bdm_count": sum(1 for m in members if m.active),  # P-01
        "figures": [
            {"key": key, "label": label, "definition": definition.format(who=who), "basis": basis, "tracked": source is not None, "value": value(key, source)}
            for key, label, definition, basis, source in rows
        ],
    }
