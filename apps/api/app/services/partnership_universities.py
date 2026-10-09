"""upc-003 (DEC-SCOPE-120, spec §3): the Global University Master's access rules, scope, codes, slugs and output.

Functions only; nothing here commits -- the route owns the transaction. Every read role reads every university (backlog convention:
"a manager reads every university"; management visibility, §27); writes are scoped:
- super_admin, overseas_admin: every university;
- partnership_head: unowned universities and those whose primary or backup manager reports to them (UM9);
- partnership_manager: universities where they are the primary or backup manager (UM4).
An id that does not exist is a 404; a role or scope refusal is a 403 (logged, ids only); a wrong state is a 409.
"""

import logging
import re
import unicodedata
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.identifiers import normalize_key
from app.models import (
    UNIVERSITY_CODE_SEQ,
    UNIVERSITY_NAME_KEY_LENGTH,
    AuditLog,
    BdmOrganization,
    Country,
    OverseasApplication,
    PartnershipProfile,
    University,
    UniversityRanking,
    User,
)
from app.partnership_stages import label_of
from app.services import partnership_tasks
from app.services.partnership import partnership_context
from app.services.partnership_milestones import expected_out
from app.services.partnership_pipeline import pipeline_out
from app.services.telecaller import person_ref

logger = logging.getLogger("app.partnership")

NOT_FOUND = "University not found"
MANAGER_INVALID = "Choose an active partnership manager from your team"
READ_ROLES = frozenset({"partnership_manager", "partnership_head", "overseas_admin", "super_admin"})
CATALOGUE_ROLES = frozenset({"partnership_head", "overseas_admin", "super_admin"})  # create, publish, deactivate (UM5, UM7, UM8)
ASSIGN_ROLES = frozenset({"partnership_head", "super_admin"})  # UM3, UM7; also reopen a lost university (upc-007 PS6)
STAGE_ROLES = frozenset({"partnership_manager", "partnership_head", "super_admin"})  # upc-007 PS5: overseas_admin reads only
CONTACT_ROLES = frozenset({"partnership_manager", "partnership_head", "super_admin"})  # upc-006 CT5: write contacts, read them in full
ROLE_REFUSALS = {
    "can_edit": "Only the university's partnership managers can edit it",
    "can_assign": "Only a partnership head can assign managers",
    "can_publish": "Your role cannot publish universities",
    "can_deactivate": "Your role cannot deactivate universities",
    "can_move_stage": "Only the university's partnership managers or their head can change its stage",
    "can_reopen": "Only a partnership head can reopen a lost university",
    "can_edit_contacts": "Only the university's partnership managers can edit its contacts",
    "can_manage_documents": "Only the university's partnership managers can manage its documents",
    "can_edit_timeline": "Only the university's partnership managers or their head can change its timeline",
}
TEAM_REFUSAL = "This university belongs to another partnership team"
OVERRIDE_ROLES = frozenset({"partnership_head", "super_admin"})  # upc-004 UD2: may add a duplicate, with a reason
MAX_MATCHES = 10
DUPLICATE_MESSAGE = "This university is already in the University Master"
INACTIVE = "Reactivate this university first"


def public_visible() -> list:
    """What the public catalogue may show (U5): published and active."""
    return [University.catalogue_visible.is_(True), University.active.is_(True)]


async def require_reader(db: AsyncSession, user: User) -> None:
    if user.role not in READ_ROLES or (user.role == "overseas_admin" and user.division != "overseas"):
        raise HTTPException(403, "University master access required")
    if user.role == "partnership_manager":
        await partnership_context(db, user)  # a manager without a profile is a 403 (upc-001)


def require_creator(user: User) -> None:
    if user.role not in CATALOGUE_ROLES:
        log("university_write_refused", user, "-", route="create")
        raise HTTPException(403, "Your role cannot add universities")


async def team_of(db: AsyncSession, user: User) -> frozenset[UUID]:
    """The head's direct reports (empty for every other role)."""
    if user.role != "partnership_head":
        return frozenset()
    return frozenset((await db.scalars(select(PartnershipProfile.user_id).where(PartnershipProfile.reporting_head_user_id == user.id))).all())


def _in_scope(user: User, uni: University, team: frozenset[UUID]) -> bool:
    owners = {uni.primary_manager_user_id, uni.backup_manager_user_id} - {None}
    if user.role in ("super_admin", "overseas_admin"):
        return True
    if user.role == "partnership_head":
        return not owners or bool(owners & team)
    return user.id in owners


_ACTION_ROLES = {
    "can_edit": READ_ROLES,
    "can_assign": ASSIGN_ROLES,
    "can_reopen": ASSIGN_ROLES,
    "can_move_stage": STAGE_ROLES,
    "can_edit_contacts": CONTACT_ROLES,
    "can_manage_documents": CONTACT_ROLES,  # upc-026 DC8: the contacts rule
    "can_edit_timeline": STAGE_ROLES,  # upc-008 MS10: the stage rule (owner / head / super_admin)
}


def _role_allows(user: User, action: str) -> bool:
    return user.role in _ACTION_ROLES.get(action, CATALOGUE_ROLES)


def permissions(user: User, uni: University, team: frozenset[UUID]) -> dict[str, bool]:
    allowed = {a: _role_allows(user, a) and _in_scope(user, uni, team) for a in ROLE_REFUSALS}
    return {a: ok and (uni.active or a == "can_deactivate") for a, ok in allowed.items()}


def require(user: User, uni: University, team: frozenset[UUID], action: str, route: str) -> None:
    """403 for the wrong role or team first (logged), then 409 for an inactive university (except de/reactivation)."""
    if not _role_allows(user, action) or not _in_scope(user, uni, team):
        log("university_write_refused", user, uni.id, route=route)
        manager_refusal = user.role == "partnership_manager" or not _role_allows(user, action)
        raise HTTPException(403, ROLE_REFUSALS[action] if manager_refusal else TEAM_REFUSAL)
    if not uni.active and action != "can_deactivate":
        raise HTTPException(409, INACTIVE)


async def load(db: AsyncSession, university_id: UUID, *, lock: bool = False) -> University:
    stmt = select(University).where(University.id == university_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    uni = await db.scalar(stmt)
    if uni is None:
        raise HTTPException(404, NOT_FOUND)
    return uni


async def country_or_422(db: AsyncSession, country_id: UUID) -> Country:
    country = await db.get(Country, country_id)
    if country is None:
        raise HTTPException(422, "Unknown country")
    return country


def check_publishable(uni: University, country: Country) -> None:
    """UM6: a public university needs catalogue content and a catalogue country (a public row in an internal country would leak it,
    upc-002 C5). Also re-checked when a published university is edited."""
    if not uni.overview.strip():
        raise HTTPException(422, "Add an overview before publishing")
    if not country.catalogue_visible:
        raise HTTPException(422, "This university's country is not in the public catalogue, so it cannot be published")


async def next_code(db: AsyncSession) -> str:
    """A sequence never repeats a value; gaps after a rollback are accepted. uq_universities_code is the backstop."""
    return f"UNV-{await db.scalar(select(UNIVERSITY_CODE_SEQ.next_value())):06d}"


def slug_base(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:110] or "university"


async def free_slug(db: AsyncSession, name: str, code: str) -> str:
    """UM14: the name's slug, or name + code when taken (the code is unique, so that one is free). A concurrent create of the same
    name can still collide on uq slug; the route turns that into a 409 to retry."""
    base = slug_base(name)
    taken = await db.scalar(select(func.count()).select_from(University).where(University.slug == base))
    return f"{base}-{code.lower()}" if taken else base


async def replace_rankings(db: AsyncSession, uni: University, rankings: list) -> None:
    for row in await rankings_of(db, uni.id):
        await db.delete(row)
    await db.flush()
    db.add_all(UniversityRanking(university_id=uni.id, **r.model_dump()) for r in rankings)


async def rankings_of(db: AsyncSession, university_id: UUID) -> list[UniversityRanking]:
    stmt = (
        select(UniversityRanking)
        .where(UniversityRanking.university_id == university_id)
        .order_by(UniversityRanking.system, func.coalesce(UniversityRanking.other_name, ""), UniversityRanking.year.desc())
    )
    return list((await db.scalars(stmt)).all())


async def application_count(db: AsyncSession, university_id: UUID) -> int:
    return await db.scalar(select(func.count()).select_from(OverseasApplication).where(OverseasApplication.university_id == university_id)) or 0


async def locked_manager(db: AsyncSession, user: User, manager_id: UUID) -> User:
    """An active partnership_manager with a profile, reporting to this head (any head for super_admin). FOR SHARE: a deactivation in
    the same instant waits for this commit. One message for every invalid target, so the route can't be used to probe users."""
    target = await db.scalar(select(User).where(User.id == manager_id).with_for_update(read=True))
    profile = await db.get(PartnershipProfile, manager_id) if target else None
    if target is None or profile is None or not target.active or target.role != "partnership_manager":
        raise HTTPException(422, MANAGER_INVALID)
    if user.role != "super_admin" and profile.reporting_head_user_id != user.id:
        raise HTTPException(422, MANAGER_INVALID)
    return target


def manager_options_filter(user: User) -> list:
    """The managers this caller may assign (UM3): a head's active direct reports; every active manager for super_admin."""
    filters = [User.role == "partnership_manager", User.active.is_(True)]
    if user.role != "super_admin":
        filters.append(PartnershipProfile.reporting_head_user_id == user.id)
    return filters


def search_filters(pattern: str | None) -> list:
    if pattern is None:
        return []
    return [or_(*(c.ilike(pattern, escape="\\") for c in (University.name, University.university_code, University.city)))]


def _country(country: Country) -> dict:
    return {"id": country.id, "name": country.name, "iso2": country.iso2, "region": country.region, "catalogue_visible": country.catalogue_visible}


def row_out(user: User, uni: University, country: Country, primary: User | None, backup: User | None, team: frozenset[UUID]) -> dict:
    return {
        "id": uni.id,
        "university_code": uni.university_code,
        "slug": uni.slug,
        "name": uni.name,
        "institution_type": uni.institution_type,
        "country": _country(country),
        "city": uni.city,
        "priority": uni.priority,
        "partnership_potential": uni.partnership_potential,
        "relationship_strength": uni.relationship_strength,
        "primary_manager": person_ref(primary) if primary else None,
        "backup_manager": person_ref(backup) if backup else None,
        "catalogue_visible": uni.catalogue_visible,
        "active": uni.active,
        "stage": uni.stage,
        "stage_label": label_of(uni.stage),
        "lost": uni.lost_at is not None,
        "permissions": permissions(user, uni, team),
    }


async def detail_out(db: AsyncSession, user: User, uni: University, team: frozenset[UUID] | None = None, *, refresh: bool = True) -> dict:
    """What every route returns. Refreshes first: server defaults (timestamps) are expired after a flush."""
    if refresh:
        await db.refresh(uni)
    team = await team_of(db, user) if team is None else team
    country = await db.get_one(Country, uni.country_id)  # NOT NULL FK
    primary = await db.get(User, uni.primary_manager_user_id) if uni.primary_manager_user_id else None
    backup = await db.get(User, uni.backup_manager_user_id) if uni.backup_manager_user_id else None
    return {
        **row_out(user, uni, country, primary, backup, team),
        **{
            k: getattr(uni, k)
            for k in (
                "ownership_type",
                "state_region",
                "website",
                "course_levels",
                "popular_programs",
                "international_office",
                "existing_relationship",
                "overview",
                "eligibility",
                "created_at",
                "updated_at",
            )
        },
        "rankings": [{"system": r.system, "other_name": r.other_name, "year": r.year, "rank": r.rank} for r in await rankings_of(db, uni.id)],
        "application_count": await application_count(db, uni.id),
        "pipeline": pipeline_out(uni),
        "linked_bdm_organizations": await linked_bdm_organizations(db, uni.id),
        "follow_up": await partnership_tasks.follow_up_out(db, uni.id),  # upc-020 TK14/TK15
        "expected": expected_out(uni),  # upc-008 §5
    }


def name_key_of(name: str) -> str:
    return normalize_key(name, UNIVERSITY_NAME_KEY_LENGTH)


def match_out(uni: University, country: Country, primary: User | None, backup: User | None) -> dict:
    """upc-004 UD5: the panel's fields. Stage, last contact and next follow-up join when upc-007/006/020 add them."""
    return {
        "id": uni.id,
        "university_code": uni.university_code,
        "name": uni.name,
        "country": {"id": country.id, "name": country.name},
        "city": uni.city,
        "active": uni.active,
        "catalogue_visible": uni.catalogue_visible,
        "existing_relationship": uni.existing_relationship,
        "primary_manager": person_ref(primary) if primary else None,
        "backup_manager": person_ref(backup) if backup else None,
    }


async def find_duplicates(db: AsyncSession, name_key: str, country_id: UUID | None = None, exclude_id: UUID | None = None) -> tuple[list[dict], int]:
    """UD1: same normalized name (+ the country when given; a BDM organization has none), inactive rows included. Ordered by code, at
    most MAX_MATCHES, on ix_universities_duplicate_key."""
    conditions = [University.name_key == name_key]
    if country_id is not None:
        conditions.append(University.country_id == country_id)
    if exclude_id is not None:
        conditions.append(University.id != exclude_id)
    total = await db.scalar(select(func.count()).select_from(University).where(*conditions))
    if not total:
        return [], 0
    primary, backup = aliased(User), aliased(User)
    stmt = (
        select(University, Country, primary, backup)
        .join(Country, Country.id == University.country_id)
        .outerjoin(primary, primary.id == University.primary_manager_user_id)
        .outerjoin(backup, backup.id == University.backup_manager_user_id)
        .where(*conditions)
        .order_by(University.university_code)
        .limit(MAX_MATCHES)
    )
    return [match_out(*row) for row in (await db.execute(stmt)).all()], total


def duplicate_lock_key(country_id: UUID, name_key: str) -> str:
    """UD4: the advisory lock text for one duplicate key, shared by a manual write and the CSV import (upc-005 IM9)."""
    return f"university:{country_id}:{name_key}"


async def check_duplicates(db: AsyncSession, user: User, name: str, country_id: UUID, reason: str | None, exclude_id: UUID | None = None) -> int:
    """UD2/UD4: the number of matches an override accepted (0 when none). A transaction lock on the key serializes two writes of the same
    name + country, so the second sees the first. Matches without an override from OVERRIDE_ROLES are a 409 carrying the panel."""
    key = name_key_of(name)
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": duplicate_lock_key(country_id, key)})
    matches, total = await find_duplicates(db, key, country_id, exclude_id)
    if not total:
        return 0
    can_override = user.role in OVERRIDE_ROLES
    if reason and can_override:
        return total
    log("university_duplicate_blocked", user, exclude_id or "-", match_count=total)
    raise HTTPException(409, {"message": DUPLICATE_MESSAGE, "code": "university_duplicate", "matches": jsonable_encoder(matches), "total": total, "can_override": can_override})


async def linked_bdm_organizations(db: AsyncSession, university_id: UUID) -> list[dict]:
    """UD11: the BDM organizations linked to this university, as text (partnership roles cannot open BDM records)."""
    stmt = select(BdmOrganization, User.full_name).join(User, User.id == BdmOrganization.assigned_bdm_user_id).where(BdmOrganization.university_id == university_id).order_by(BdmOrganization.code)
    return [
        {"id": o.id, "code": o.code, "name": o.name, "city": o.city, "bdm_type": o.bdm_type, "assigned_bdm_name": bdm_name, "archived": o.archived_at is not None}
        for o, bdm_name in (await db.execute(stmt)).all()
    ]


def audit(db: AsyncSession, user: User, action: str, university_id: UUID, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, codes and field names only."""
    db.add(AuditLog(user_id=user.id, action=f"university.{action}", entity_type="university", entity_id=str(university_id), metadata_json=metadata or {}))


def log(event: str, user: User, university_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "university_id": str(university_id), **extra}})
