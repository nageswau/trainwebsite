"""bdm-002 (DEC-SCOPE-060, spec §5.2): organization scope, permissions, duplicates, codes and output.

Functions only; nothing here commits -- the route owns the transaction. Every route resolves an organization through `load_scoped`,
so an id outside the caller's scope is the same 404 as a missing one. Logs carry ids, route and counts, never names, phones or emails.
"""

import logging
import unicodedata
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BDM_APPOINTMENT_OPEN,
    BDM_ORGANIZATION_CODE_SEQ,
    BDM_PROFILE_FIELDS,
    BDM_PROFILE_GROUP,
    AuditLog,
    BdmAppointment,
    BdmOrganization,
    BdmOrganizationContact,
    BdmProfile,
    User,
)
from app.schemas import BDM_ORG_LABELS
from app.services.bdm import bdm_context, person_ref
from app.services.bdm_pipeline import pipeline_out

logger = logging.getLogger("app.bdm")

NOT_FOUND = "Organization not found"
CONTACT_NOT_FOUND = "Contact not found"
REASSIGN_INVALID = "Choose an active BDM of this type from your team"
MAX_DUPLICATE_MATCHES = 10
NAME_KEY_LENGTH = BdmOrganization.__table__.c.name_key.type.length
CITY_KEY_LENGTH = BdmOrganization.__table__.c.city_key.type.length
REFUSALS = {
    "can_edit": "Only the assigned BDM can edit this organization",
    "can_archive": "Only the assigned BDM can archive this organization",
    "can_restore": "Only the BDM's manager can restore this organization",
    "can_reassign": "Only the BDM's manager can reassign this organization",
}
STATE_REFUSALS = {  # C15: the 409 when the role is right but the archived state is wrong
    "can_edit": "Restore this organization first",
    "can_archive": "Already archived",
    "can_restore": "Already active",
    "can_reassign": "Restore this organization first",
}
# bdm-003 (spec §5.2): the type words in the profile 422s and the type-change 409 (a profile group is named like its org type); field
# names come from schemas.BDM_ORG_LABELS, the same words as the field's own 422s.
ORG_TYPE_LABELS = {
    "college": "College", "university": "University", "agent": "Agent", "school": "School", "corporate": "Corporate",
    "training_institute": "Training Institute", "other": "Other",
}
GRADE_ORDER = "Lowest grade can't be above the highest grade"


def normalize_key(value: str, limit: int) -> str:
    """Q-18's "normalized name / city": NFKC (full-width and compatibility forms), whitespace collapsed, casefolded. NFKC and casefold
    can lengthen text ("ß" -> "ss"), so the key is cut to its column length (final review M2); two names that differ only past that
    point still match, which a warning can afford."""
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()[:limit]


def org_keys(name: str, city: str) -> tuple[str, str]:
    return normalize_key(name, NAME_KEY_LENGTH), normalize_key(city, CITY_KEY_LENGTH)


def format_code(n: int) -> str:
    return f"ORG-{n:06d}"  # Python formatting grows past six digits; SQL lpad would truncate


async def next_code(db: AsyncSession) -> str:
    """C4: a sequence never repeats a value; gaps after a rollback are accepted. uq_bdm_organizations_code is the backstop."""
    return format_code(await db.scalar(select(BDM_ORGANIZATION_CODE_SEQ.next_value())))


async def caller_scope(db: AsyncSession, user: User) -> list:
    """Read scope as SQL filters (Q-02, C2, C14). Any other role is 403 (C7). The manager filter is a sub-select, not a join, so
    `FOR UPDATE` on an organization never locks a `bdm_profiles` row."""
    if user.role == "bdm":
        profile = await bdm_context(db, user)
        return [BdmOrganization.bdm_type == profile.bdm_type]
    if user.role == "bdm_manager":
        team = select(BdmProfile.user_id).where(BdmProfile.reporting_manager_user_id == user.id)
        return [BdmOrganization.assigned_bdm_user_id.in_(team)]
    if user.role == "super_admin":
        return []
    raise HTTPException(403, "BDM role required")


async def load_scoped(db: AsyncSession, user: User, org_id: UUID, *, lock: bool = False) -> BdmOrganization:
    stmt = select(BdmOrganization).where(BdmOrganization.id == org_id, *await caller_scope(db, user))
    if lock:
        stmt = stmt.with_for_update(of=BdmOrganization).execution_options(populate_existing=True)
    org = await db.scalar(stmt)
    if org is None:
        raise HTTPException(404, NOT_FOUND)
    return org


def _allowed(user: User, org: BdmOrganization, action: str) -> bool:
    """Role half of a permission, for an organization already in the caller's scope (load_scoped)."""
    if action in ("can_edit", "can_archive"):
        return user.role == "super_admin" or (user.role == "bdm" and org.assigned_bdm_user_id == user.id)
    return user.role in ("bdm_manager", "super_admin")


def permissions(user: User, org: BdmOrganization) -> dict[str, bool]:
    archived = org.archived_at is not None
    return {a: _allowed(user, org, a) and (archived if a == "can_restore" else not archived) for a in REFUSALS}


def require(user: User, org: BdmOrganization, action: str, route: str) -> None:
    """403 for the wrong role first (logged), then 409 for the wrong state (C15)."""
    if not _allowed(user, org, action):
        logger.warning("bdm_org_write_refused", extra={"extra_fields": {"actor_id": str(user.id), "org_id": str(org.id), "route": route, "action": action}})
        raise HTTPException(403, REFUSALS[action])
    if not permissions(user, org)[action]:
        raise HTTPException(409, STATE_REFUSALS[action])


async def find_duplicates(db: AsyncSession, bdm_type: str, name_key: str, city_key: str, exclude_id: UUID | None = None) -> tuple[list[dict], int]:
    """Q-18 / C8: same module + normalized name + city, archived included. Never crosses modules, so it shows only what the
    caller can already read."""
    conditions = [BdmOrganization.bdm_type == bdm_type, BdmOrganization.name_key == name_key, BdmOrganization.city_key == city_key]
    if exclude_id is not None:
        conditions.append(BdmOrganization.id != exclude_id)
    total = await db.scalar(select(func.count()).select_from(BdmOrganization).where(*conditions))
    if not total:
        return [], 0
    rows = (
        await db.execute(
            select(BdmOrganization, User.full_name).join(User, User.id == BdmOrganization.assigned_bdm_user_id).where(*conditions).order_by(BdmOrganization.code).limit(MAX_DUPLICATE_MATCHES)
        )
    ).all()
    matches = [{"id": str(o.id), "code": o.code, "name": o.name, "city": o.city, "archived": o.archived_at is not None, "assigned_bdm_name": name} for o, name in rows]
    return matches, total


def duplicate_conflict(matches: list[dict], total: int) -> HTTPException:
    return HTTPException(409, {"message": "A similar organization already exists in your module", "code": "possible_duplicate", "matches": matches, "total": total})


async def contacts_of(db: AsyncSession, org_id: UUID) -> list[BdmOrganizationContact]:
    """Insertion order (`position`); the primary is picked out by the caller."""
    stmt = select(BdmOrganizationContact).where(BdmOrganizationContact.organization_id == org_id).order_by(BdmOrganizationContact.position)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


async def load_contact(db: AsyncSession, org: BdmOrganization, contact_id: UUID) -> BdmOrganizationContact:
    contact = await db.scalar(select(BdmOrganizationContact).where(BdmOrganizationContact.id == contact_id, BdmOrganizationContact.organization_id == org.id))
    if contact is None:
        raise HTTPException(404, CONTACT_NOT_FOUND)
    return contact


async def make_primary(db: AsyncSession, contacts: list[BdmOrganizationContact], target: BdmOrganizationContact) -> None:
    """Clear first and flush, so the partial unique index never sees two primaries in one statement batch."""
    for contact in contacts:
        if contact is not target and contact.is_primary:
            contact.is_primary = False
    await db.flush()
    target.is_primary = True
    await db.flush()


async def locked_reassign_target(db: AsyncSession, user: User, org: BdmOrganization, bdm_user_id: UUID) -> User:
    """C2/AC4: an active `bdm` of the organization's type who reports to this manager (any team for super_admin). FOR SHARE on the
    user row: a deactivation in the same instant waits for this commit (bdm-001's locked_active_manager pattern). One message for
    every invalid target, so the route can't be used to probe users (§12.3)."""
    if bdm_user_id == org.assigned_bdm_user_id:
        raise HTTPException(409, "Already assigned to this BDM")
    target = await db.scalar(select(User).where(User.id == bdm_user_id).with_for_update(read=True))
    profile = await db.scalar(select(BdmProfile).where(BdmProfile.user_id == bdm_user_id)) if target else None
    valid = (
        target is not None
        and target.active
        and target.role == "bdm"
        and profile is not None
        and profile.bdm_type == org.bdm_type
        and (user.role == "super_admin" or profile.reporting_manager_user_id == user.id)
    )
    if not valid:
        raise HTTPException(422, REASSIGN_INVALID)
    return target


def meeting_columns():
    """bdm-006's Last / Next meeting (spec §5.6) as correlated scalar subqueries on ix_bdm_appointments_org_starts -- across every BDM's
    appointments at the organization, so readers see when, never who or what."""
    last = (
        select(func.max(BdmAppointment.starts_at))
        .where(BdmAppointment.organization_id == BdmOrganization.id, BdmAppointment.status == "completed")
        .correlate(BdmOrganization)
        .scalar_subquery()
        .label("last_meeting_at")
    )
    upcoming = (
        select(func.min(BdmAppointment.starts_at))
        .where(BdmAppointment.organization_id == BdmOrganization.id, BdmAppointment.status.in_(BDM_APPOINTMENT_OPEN), BdmAppointment.starts_at > func.now())
        .correlate(BdmOrganization)
        .scalar_subquery()
        .label("next_meeting_at")
    )
    return last, upcoming


def profile_group(org_type: str) -> str | None:
    return BDM_PROFILE_GROUP.get(org_type)


def _profile_error(key: str, msg: str, value) -> dict:
    return {"type": "value_error", "loc": ("body", "profile", key), "msg": msg, "input": value}


def check_profile(org_type: str, sent: dict, stored: BdmOrganization | None) -> None:
    """spec §5.2 (AC2, AC6): the keys the effective org_type accepts -- by presence, so {"board": null} on a College is refused too -- and
    the grade order on the stored values overlaid by the sent ones. One 422 in FastAPI's own shape, each error at its field (the
    agent_visa precedent), so the form can mark the field. Runs after the row lock on PATCH, so `stored` is current."""
    allowed = BDM_PROFILE_FIELDS.get(profile_group(org_type), ())
    errors = [_profile_error(k, f"{BDM_ORG_LABELS[k]} is not a field for {ORG_TYPE_LABELS[org_type]} organizations", v) for k, v in sent.items() if k not in allowed]
    if not errors and "grade_from" in allowed:
        low, high = (sent[k] if k in sent else getattr(stored, k, None) for k in ("grade_from", "grade_to"))
        if low is not None and high is not None and low > high:
            errors.append(_profile_error("grade_to", GRADE_ORDER, sent.get("grade_to", high)))
    if errors:
        raise RequestValidationError(errors)


def check_type_change(user: User, org: BdmOrganization, new_type: str) -> None:
    """P4 / AC5: a type change into another profile group is a 409 while the old group has data; the BDM clears it first. College <->
    University share a group. Structured like possible_duplicate, so the form names the fields without parsing text (§12.1 A1)."""
    old = profile_group(org.org_type)
    if old is None or old == profile_group(new_type):
        return
    filled = [k for k in BDM_PROFILE_FIELDS[old] if getattr(org, k) is not None]
    if filled:
        log("bdm_org_type_change_refused", user, org.id, from_group=old, fields=filled)
        raise HTTPException(409, {"message": f"Clear the {ORG_TYPE_LABELS[old]} details before changing the type", "code": "profile_not_empty", "fields": filled})


def profile_out(org: BdmOrganization) -> dict | None:
    group = profile_group(org.org_type)
    return None if group is None else {"kind": group, **{k: getattr(org, k) for k in BDM_PROFILE_FIELDS[group]}}




def _primary(contact: BdmOrganizationContact | None) -> dict | None:
    if contact is None:
        return None
    return {"name": contact.name, "designation": contact.designation, "phone": contact.phone, "email": contact.email}


def _contact(contact: BdmOrganizationContact) -> dict:
    return {k: getattr(contact, k) for k in ("id", "name", "designation", "role", "phone", "email", "is_primary")}


def row_out(user: User, org: BdmOrganization, assignee: User, primary: BdmOrganizationContact | None, last_meeting_at=None, next_meeting_at=None) -> dict:
    return {
        "id": org.id,
        "code": org.code,
        "name": org.name,
        "org_type": org.org_type,
        "bdm_type": org.bdm_type,
        "city": org.city,
        "state": org.state,
        "existing_partner": org.existing_partner,
        "assigned_bdm": person_ref(assignee),
        "primary_contact": _primary(primary),
        "archived": org.archived_at is not None,
        "last_meeting_at": last_meeting_at,
        "next_meeting_at": next_meeting_at,
        "permissions": permissions(user, org),
    }


async def organization_out(db: AsyncSession, user: User, org: BdmOrganization, *, refresh: bool = True) -> dict:
    """The detail every route returns (§12.1 A1). Refreshes first: server defaults (timestamps) are expired after a flush."""
    from app.services.bdm_onboarding import org_onboarding_out  # local: bdm_onboarding imports this module

    if refresh:
        await db.refresh(org)
    contacts = await contacts_of(db, org.id)
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_({org.assigned_bdm_user_id, org.created_by_user_id})))).all()}
    primary = next((c for c in contacts if c.is_primary), None)
    ordered = ([primary] if primary else []) + [c for c in contacts if c is not primary]
    last_meeting_at, next_meeting_at = (await db.execute(select(*meeting_columns()).select_from(BdmOrganization).where(BdmOrganization.id == org.id))).one()
    return {
        **row_out(user, org, people[org.assigned_bdm_user_id], primary, last_meeting_at, next_meeting_at),
        "phone": org.phone,
        "email": org.email,
        "website": org.website,
        "address": org.address,
        "courses_interested": org.courses_interested,
        "student_count": org.student_count,
        "profile": profile_out(org),
        "pipeline": pipeline_out(org),  # bdm-004
        "onboarding": await org_onboarding_out(db, user, org),  # bdm-018
        "contacts": [_contact(c) for c in ordered],
        "created_by_name": people[org.created_by_user_id].full_name,
        "archived_at": org.archived_at,
        "created_at": org.created_at,
        "updated_at": org.updated_at,
    }


def audit(db: AsyncSession, user: User, action: str, org_id: UUID, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, field names and counts only."""
    db.add(AuditLog(user_id=user.id, action=f"bdm_organization.{action}", entity_type="bdm_organization", entity_id=str(org_id), metadata_json=metadata or {}))


def log(event: str, user: User, org_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "org_id": str(org_id), **extra}})
