"""tel-025 (DEC-SCOPE-104, spec §3): telecaller deactivation, team move and handover of open leads, and telecaller manager deactivation.

Functions only; nothing here commits -- the route owns the transaction. Lock order everywhere: the source's open leads (by id), then
its profile, then its user (FOR UPDATE), then the target (FOR SHARE) -- the lead-before-profile order of tel-007's manual assignment, so
the two cannot deadlock. Open follow-ups and appointments belong to the lead (tel-011 F3, tel-016), so they move with it untouched.
Logs and audit metadata carry ids and counts, never names, phones or emails."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.workflows import _notify_user
from app.lead_stages import CLOSED
from app.models import LEAD_APPOINTMENT_OPEN, Appointment, AuditLog, Enquiry, LeadFollowUp, TelDistributionRule, TelecallerProfile, User
from app.services import lead_distribution
from app.services.provisioning import revoke_welcome_tokens
from app.services.telecaller import TEAM_LABEL, locked_active_manager, require_creator_may

logger = logging.getLogger("app.telecaller")

TARGET_REQUIRED = "Choose who takes over this telecaller's open leads"
TARGET_INVALID = "Choose an active telecaller of the same team"
MANAGER_TARGET_INVALID = "Choose another active telecaller manager"
FINISHED = ("converted", *sorted(CLOSED))  # LC2: a closed or converted lead keeps its telecaller (history and credit, AC2)


def _plural(n: int, singular: str, plural: str | None = None) -> str:
    return f"{n} {singular if n == 1 else plural or singular + 's'}"


def open_leads(user_id: UUID) -> list:
    return [Enquiry.telecaller_user_id == user_id, Enquiry.status.notin_(FINISHED)]


async def open_work(db: AsyncSession, user_id: UUID) -> dict[str, int]:
    lead_ids = select(Enquiry.id).where(*open_leads(user_id))

    async def count(model, *where) -> int | None:
        return await db.scalar(select(func.count()).select_from(model).where(*where))

    return {
        "leads": await count(Enquiry, *open_leads(user_id)) or 0,
        "follow_ups": await count(LeadFollowUp, LeadFollowUp.lead_id.in_(lead_ids), LeadFollowUp.status == "open") or 0,
        "appointments": await count(Appointment, Appointment.lead_id.in_(lead_ids), Appointment.status.in_(LEAD_APPOINTMENT_OPEN)) or 0,
    }


async def load_telecaller(db: AsyncSession, actor: User, user_id: UUID, route: str) -> TelecallerProfile:
    """404 unless a telecaller with a profile; then 403 unless the actor manages that team (LC1)."""
    user = await db.get(User, user_id)
    profile = await db.scalar(select(TelecallerProfile).where(TelecallerProfile.user_id == user_id)) if user and user.role == "telecaller" else None
    if profile is None:
        raise HTTPException(404, "Telecaller not found")
    require_creator_may(actor, profile.team, route)
    return profile


async def lock_source(db: AsyncSession, user_id: UUID) -> tuple[User, TelecallerProfile, list[Enquiry]]:
    """The open leads, the profile and the user, each FOR UPDATE and re-read, so every check sees committed values."""
    leads = (await db.scalars(select(Enquiry).where(*open_leads(user_id)).order_by(Enquiry.id).with_for_update()
                              .execution_options(populate_existing=True))).all()
    profile = (await db.execute(select(TelecallerProfile).where(TelecallerProfile.user_id == user_id).with_for_update()
                                .execution_options(populate_existing=True))).scalar_one()
    user = (await db.execute(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))).scalar_one()
    return user, profile, list(leads)


async def locked_target(db: AsyncSession, source: User, team: str, target: str | None, reassign_to: UUID | None, has_work: bool) -> User | None:
    """LC3: None means the team's unassigned queue. A telecaller target is read FOR SHARE (a deactivation of it in the same instant waits
    for this commit); every invalid one gets the same message, so the route can't be used to probe users."""
    if has_work and target is None:
        raise HTTPException(422, TARGET_REQUIRED)
    if target != "telecaller":
        return None
    row = None if reassign_to == source.id else (await db.execute(
        select(User, TelecallerProfile).join(TelecallerProfile, TelecallerProfile.user_id == User.id)
        .where(User.id == reassign_to, User.role == "telecaller").with_for_update(read=True)
    )).first()
    if row is None or not row[0].active or row[1].team != team:
        raise HTTPException(422, TARGET_INVALID)
    return row[0]


async def move_leads(db: AsyncSession, actor: User, leads: list[Enquiry], target: User | None, method: str) -> None:
    """One `lead.assign` audit row per lead (tel-007 D4). To a telecaller through tel-007's `assign` (a new lead gets its `assigned`
    event); to the queue the lead just loses its telecaller and keeps its stage."""
    for lead in leads:
        if target is not None:
            await lead_distribution.assign(db, lead, target.id, method, actor, notify=False)  # D6 tells the target once (tel-020 AL13)
            continue
        before, lead.telecaller_user_id = lead.telecaller_user_id, None
        db.add(AuditLog(user_id=actor.id, action="lead.assign", entity_type="enquiry", entity_id=str(lead.id),
                        metadata_json={"from": str(before), "to": None, "method": method}))


async def remove_rules(db: AsyncSession, actor: User, user_id: UUID) -> int:
    """D3: the telecaller's routing rules could never fire again (rules pick active telecallers of the rule's team); each is audited as
    a manager's delete is."""
    rules = (await db.scalars(delete(TelDistributionRule).where(TelDistributionRule.telecaller_user_id == user_id)
                              .returning(TelDistributionRule).execution_options(synchronize_session=False))).all()
    for rule in rules:
        db.add(AuditLog(user_id=actor.id, action="telecaller.rule_delete", entity_type="tel_distribution_rule", entity_id=str(rule.id),
                        metadata_json={"team": rule.team, "kind": rule.kind, "telecaller_user_id": str(user_id), "reason": "telecaller_lifecycle"}))
    return len(rules)


async def deactivate_user(db: AsyncSession, user: User) -> None:
    """D1: the session ends at once (AGN-002 `session_version`); open welcome links are revoked (ENH-003)."""
    user.active = False
    user.session_version += 1
    await revoke_welcome_tokens(db, user.id)


async def change_team(db: AsyncSession, actor: User, user: User, profile: TelecallerProfile, team: str, manager_id: UUID | None) -> None:
    """T22 / D2: the division follows the team; the old token carries the old division, so the session ends."""
    if manager_id is not None and manager_id != profile.reporting_manager_user_id:
        await locked_active_manager(db, manager_id)
        profile.reporting_manager_user_id = manager_id
    profile.team = user.division = team
    user.session_version += 1


def require_new_team(actor: User, profile: TelecallerProfile, team: str, route: str) -> None:
    require_creator_may(actor, team, route)  # LC1: the actor must manage both teams
    if team == profile.team:
        raise HTTPException(422, f"This telecaller is already on the {TEAM_LABEL[team]} team")


async def notify_target(db: AsyncSession, source: User, target: User | None, moved: dict[str, int]) -> None:
    """D6: in-app + email (ENH-014 queue, sent after commit)."""
    if target is not None and moved["leads"]:
        await _notify_user(db, target, "Leads handed over to you", f"{_plural(moved['leads'], 'lead')} from {source.full_name} are now yours.",
                           "/telecaller/leads")


# --- telecaller managers (D4) ----------------------------------------------------------------------------------------------------

async def team_size(db: AsyncSession, manager_id: UUID) -> int:
    """Every telecaller reporting to the manager, active or not (an inactive one may be reactivated under them)."""
    return await db.scalar(select(func.count()).select_from(TelecallerProfile).where(TelecallerProfile.reporting_manager_user_id == manager_id)) or 0


async def lock_manager(db: AsyncSession, manager_id: UUID) -> User:
    """404 unless a telecaller manager. Its reports' profiles FOR UPDATE, then the manager FOR UPDATE -- the profile-before-manager order
    of `admin.update_user`, whose manager check takes FOR SHARE on the manager."""
    manager = await db.get(User, manager_id)
    if manager is None or manager.role != "telecaller_manager":
        raise HTTPException(404, "Telecaller manager not found")
    await db.execute(select(TelecallerProfile.id).where(TelecallerProfile.reporting_manager_user_id == manager_id).with_for_update())
    return (await db.execute(select(User).where(User.id == manager_id).with_for_update().execution_options(populate_existing=True))).scalar_one()


async def locked_manager_target(db: AsyncSession, source: User, target_id: UUID | None) -> User:
    target = None if target_id in (None, source.id) else await db.scalar(select(User).where(User.id == target_id).with_for_update(read=True))
    if target is None or not target.active or target.role != "telecaller_manager":
        raise HTTPException(422, MANAGER_TARGET_INVALID)
    return target


async def move_reports(db: AsyncSession, source: User, target: User) -> list[UUID]:
    stmt = (update(TelecallerProfile).where(TelecallerProfile.reporting_manager_user_id == source.id)
            .values(reporting_manager_user_id=target.id).returning(TelecallerProfile.user_id))
    return list((await db.execute(stmt.execution_options(synchronize_session=False))).scalars().all())


# --- the plain PATCH /admin/users path (D5) --------------------------------------------------------------------------------------

async def plain_deactivation(db: AsyncSession, actor: User, user: User) -> None:
    """A telecaller with open leads, or a manager with reports, is deactivated only from the Telecallers page, choosing who takes over
    (422, not 409: the Users page reads 409 as the trainer "confirm cascade" prompt). Otherwise the same session and rule effects."""
    if user.role == "telecaller":
        if n := (await open_work(db, user.id))["leads"]:
            raise HTTPException(422, f"This telecaller has {_plural(n, 'open lead')}. Deactivate them from the Telecallers page, choosing who takes over")
        await remove_rules(db, actor, user.id)
    elif user.role == "telecaller_manager":
        if n := await team_size(db, user.id):
            raise HTTPException(422, f"This manager has {_plural(n, 'telecaller')}. Deactivate them from the Telecallers page (Telecaller managers), choosing who takes over")
    else:
        return
    user.session_version += 1


def log(event: str, actor: User, **fields) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(actor.id), **fields}})
