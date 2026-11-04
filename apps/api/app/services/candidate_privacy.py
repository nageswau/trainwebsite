"""hrc-035 (DEC-SCOPE-396, spec docs/superpowers/specs/2026-11-04-hrc-035-candidate-privacy-design.md): the staff-recorded lawful basis
(K1/K2), the anonymiser (K3), the hold rule (K5), the candidate's deletion request and the HR Manager's decision (K6/K7), the retention
rule and its sweep (K8) and what a deactivated staff member gives up (K9).

Functions only; nothing here commits except the beat sweep, which owns its session. Stored files are deleted only after the commit that
removed their rows (`purge_files`). Logs and audit rows carry ids and counts -- never a name, email, phone or reason text."""

import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import String, cast, delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CANDIDATE_LAWFUL_BASES,
    AuditLog,
    Candidate,
    CandidateCertification,
    CandidateCollaborator,
    CandidateConsent,
    CandidateDocument,
    CandidateDocumentRequest,
    CandidateDuplicate,
    CandidateEducation,
    CandidateEmployment,
    CandidateNote,
    CandidateResume,
    CandidateRetentionSetting,
    CandidateTask,
    CareerApplication,
    DataSubjectRequest,
    JobApplication,
    JobOffer,
    NotificationPreference,
    ProfileShareItem,
    RecruiterCall,
    RecruiterMessage,
    User,
    UserVerificationToken,
)
from app.services import candidate_ownership as ownership
from app.services.permissions import has_grant
from app.services.storage import storage

logger = logging.getLogger("app.candidate_privacy")

PORTAL_ROLE = "candidate"  # hrc-022's external candidate role (candidate_portal.ROLE; not imported: that module imports this one)
STAFF_CONSENT_VERSION = "staff-v1"
ANONYMISED_NAME = "Anonymised candidate"
REMOVED = "[removed]"
HOLD_OFFERS = ("offer_pending", "offer_received")
CLOSED_APPLICATIONS = ("joined", "rejected", "withdrawn")
REASON_LIMIT = 500
BATCH = 100
MAX_BATCHES = 50
MONTHS_RANGE = (6, 120)
# K9: the candidate-access staff roles whose deactivation did not already end the session (recruiters: rec-037; telecallers: tel-025)
SESSION_ROLES = frozenset({"placement_officer", "placement_manager", "hr_team", "hr_manager"})

NOT_FOUND = "Request not found"
DECIDED = "This request has already been decided"
HELD = "This candidate has an offer in progress. Decide the offer first, then approve the deletion."
NO_ERASE = "Only the HR Manager can review candidate data requests"
PERIOD = f"Choose between {MONTHS_RANGE[0]} and {MONTHS_RANGE[1]} months, or turn the rule off"


# --- K1/K2 the lawful basis ----------------------------------------------------------------------------------------------------------
def basis(value) -> str | None:
    """The optional `lawful_basis` a staff create or import sends: omitted (older clients) = None, anything else must be a known basis."""
    if value is None:
        return None
    if value not in CANDIDATE_LAWFUL_BASES:
        raise HTTPException(422, "Choose why EduSphere may hold this candidate's details")
    return value


def record_staff_basis(db: AsyncSession, user: User, candidate_ids: list[UUID], source: str, lawful_basis: str | None) -> None:
    if lawful_basis is None:
        return
    for candidate_id in candidate_ids:
        db.add(CandidateConsent(candidate_id=candidate_id, user_id=user.id, action="opt_in", consent_version=STAFF_CONSENT_VERSION, source=source,
                                lawful_basis=lawful_basis))  # fmt: skip


async def latest_consent(db: AsyncSession, candidate_id: UUID) -> dict | None:
    row = await db.scalar(select(CandidateConsent).where(CandidateConsent.candidate_id == candidate_id)
                          .order_by(CandidateConsent.created_at.desc(), CandidateConsent.id.desc()).limit(1))  # fmt: skip
    if row is None:
        return None
    return {"action": row.action, "source": row.source, "lawful_basis": row.lawful_basis, "consent_version": row.consent_version, "recorded_at": row.created_at}


# --- K5 the hold -----------------------------------------------------------------------------------------------------------------------
def _offer_in_progress():
    return (select(JobOffer.id).join(JobApplication, JobApplication.id == JobOffer.application_id)
            .where(JobApplication.candidate_id == Candidate.id, JobOffer.status.in_(HOLD_OFFERS)).exists())  # fmt: skip


async def held(db: AsyncSession, candidate_id: UUID) -> bool:
    return bool(await db.scalar(select(Candidate.id).where(Candidate.id == candidate_id, _offer_in_progress())))


# --- K3 the anonymiser -----------------------------------------------------------------------------------------------------------------
CLEARED = (
    "mobile", "mobile_normalized", "linkedin", "college", "current_company", "city", "location", "source_detail", "email_verified_at",
    "current_salary", "expected_salary", "minimum_salary", "current_salary_currency", "current_salary_period", "expected_salary_currency",
    "expected_salary_period", "minimum_salary_currency", "minimum_salary_period", "salary_negotiable", "current_annual_inr",
    "expected_annual_inr", "minimum_annual_inr", "notice_days", "available_from", "preferred_contact",
)  # fmt: skip


# a website application's resume URL is what the client sent: only a key /public/career-upload itself generated is ever deleted
CAREER_KEY = re.compile(r"career-resumes/[0-9a-f]{32}(\.[a-z0-9]{1,9})?$")


def _placeholder_email(candidate: Candidate) -> str:
    """ck_candidates_contact needs a mobile or an email: a unique, undeliverable placeholder (SEC-002's `deleted-<id>` idiom)."""
    return f"anonymised-{candidate.id}@deleted.local"


async def _close_portal_account(db: AsyncSession, user_id: UUID) -> None:
    account = await db.scalar(select(User).where(User.id == user_id).with_for_update())
    if account is None or account.role != PORTAL_ROLE:
        return
    account.full_name, account.phone, account.profile = "Deleted user", None, {}
    account.email, account.active = f"deleted-{account.id}@deleted.local", False
    account.session_version += 1
    await db.execute(delete(NotificationPreference).where(NotificationPreference.user_id == account.id))
    await db.execute(delete(UserVerificationToken).where(UserVerificationToken.user_id == account.id))


async def anonymise(db: AsyncSession, candidate: Candidate, reason: str, actor_id: UUID | None) -> list[str]:
    """K3 on a locked candidate; returns the storage keys to delete after the commit. A student's candidate is refused by the callers."""
    cid, now = candidate.id, datetime.now(UTC)
    keys: list[str] = []
    for model in (CandidateResume, CandidateDocument):
        for storage_key, preview_key in (await db.execute(select(model.storage_key, model.preview_key).where(model.candidate_id == cid))).all():
            keys += [k for k in (storage_key, preview_key) if k]
    website_files = (await db.scalars(select(CareerApplication.resume_url).where(CareerApplication.candidate_id == cid))).all()
    keys += [m.group(0) for url in website_files if url and (m := CAREER_KEY.search(url))]

    resume_ids = select(CandidateResume.id).where(CandidateResume.candidate_id == cid)
    await db.execute(update(ProfileShareItem).where(ProfileShareItem.resume_id.in_(resume_ids)).values(resume_id=None))
    await db.execute(update(JobApplication).where(JobApplication.candidate_id == cid).values(resume_url=None))
    for model in (CandidateDocument, CandidateDocumentRequest, CandidateResume, CandidateEducation, CandidateEmployment, CandidateCertification,
                  CandidateNote, CandidateCollaborator):  # fmt: skip
        await db.execute(delete(model).where(model.candidate_id == cid))
    await db.execute(delete(CandidateDuplicate).where(or_(CandidateDuplicate.candidate_id == cid, CandidateDuplicate.other_id == cid)))
    await db.execute(update(CandidateTask).where(CandidateTask.candidate_id == cid).values(title=REMOVED, notes=None))
    await db.execute(update(RecruiterCall).where(RecruiterCall.candidate_id == cid).values(notes=None))
    await db.execute(update(RecruiterMessage).where(RecruiterMessage.candidate_id == cid).values(body=REMOVED, subject=None))
    await db.execute(update(ProfileShareItem).where(ProfileShareItem.candidate_id == cid).values(feedback=None))
    await db.execute(update(CareerApplication).where(CareerApplication.candidate_id == cid)
                     .values(full_name=ANONYMISED_NAME, email=func.concat("anonymised-", cast(CareerApplication.id, String), "@deleted.local"),
                             phone=None, cover_note=None, resume_url=""))  # fmt: skip
    await db.execute(update(CandidateConsent).where(CandidateConsent.candidate_id == cid).values(ip_address=None))
    # the candidate's own audit rows keep who/what/when; their before/after values (names, emails, salaries) go
    await db.execute(text("UPDATE audit_logs SET metadata_json = (metadata_json::jsonb - 'changes')::json "
                          "WHERE entity_type = 'candidates' AND entity_id = :id AND jsonb_exists(metadata_json::jsonb, 'changes')"), {"id": str(cid)})  # fmt: skip
    for field in CLEARED:
        setattr(candidate, field, None)
    candidate.name, candidate.email = ANONYMISED_NAME, _placeholder_email(candidate)
    for field in ("preferred_locations", "tools", "languages", "preferred_roles"):
        setattr(candidate, field, [])
    candidate.anonymised_at, candidate.anonymised_reason = now, reason
    candidate.archived_at = candidate.archived_at or now
    candidate.updated_at = now
    if candidate.user_id:
        await _close_portal_account(db, candidate.user_id)
    db.add(AuditLog(user_id=actor_id, action="candidate.anonymised", entity_type="candidates", entity_id=str(cid),
                    metadata_json={"reason": reason, "files": len(keys)}))  # fmt: skip
    return keys


def purge_files(keys: list[str]) -> None:
    """After the commit: a failed delete is logged by count (the rows are already gone, so nothing links to the file)."""
    failed = 0
    for key in keys:
        try:
            storage.delete(key)
        except Exception:
            failed += 1
    if failed:
        logger.warning("candidate_files_orphaned", extra={"extra_fields": {"count": failed}})


# --- K6 the candidate's own request ----------------------------------------------------------------------------------------------------
def request_out(item: DataSubjectRequest | None) -> dict | None:
    if item is None:
        return None
    return {"status": item.status, "requested_at": item.created_at, "decided_at": item.fulfilled_at, "rejection_reason": item.rejection_reason}


async def own_request(db: AsyncSession, user: User) -> DataSubjectRequest | None:
    return await db.scalar(select(DataSubjectRequest).where(DataSubjectRequest.requesting_user_id == user.id, DataSubjectRequest.type == "delete")
                           .order_by(DataSubjectRequest.created_at.desc(), DataSubjectRequest.id.desc()).limit(1))  # fmt: skip


async def request_erasure(db: AsyncSession, user: User) -> tuple[DataSubjectRequest, bool]:
    """One open request per candidate: the user row is locked, so two clicks make one request (the second gets it back, not created)."""
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    current = await own_request(db, user)
    if current is not None and current.status == "in_progress":
        return current, False
    item = DataSubjectRequest(requesting_user_id=user.id, type="delete", status="in_progress", idempotency_key=f"hrc035-{datetime.now(UTC).isoformat()}")
    db.add(item)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="gdpr.delete.request", entity_type="data_subject_request", entity_id=str(item.id), metadata_json={"status": item.status, "candidate": True}))
    logger.info("candidate_erasure_requested", extra={"extra_fields": {"user_id": str(user.id), "request_id": str(item.id)}})
    return item, True


# --- K7 the HR Manager's queue ---------------------------------------------------------------------------------------------------------
async def require_eraser(db: AsyncSession, user: User) -> None:
    if user.role != "super_admin" and not await has_grant(db, user.role, "candidates", "erase"):
        raise HTTPException(403, NO_ERASE)


def _queue_stmt():
    open_apps = (select(func.count()).select_from(JobApplication)
                 .where(JobApplication.candidate_id == Candidate.id, JobApplication.status.notin_(CLOSED_APPLICATIONS)).scalar_subquery())  # fmt: skip
    return (select(DataSubjectRequest, Candidate, open_apps.label("open_applications"), _offer_in_progress().label("held"))
            .join(User, User.id == DataSubjectRequest.requesting_user_id)
            .outerjoin(Candidate, Candidate.user_id == User.id)
            .where(DataSubjectRequest.type == "delete", User.role == PORTAL_ROLE))  # fmt: skip


def _row_out(item: DataSubjectRequest, candidate: Candidate | None, open_applications: int, is_held: bool) -> dict:
    return {
        "id": item.id, "status": item.status, "requested_at": item.created_at, "decided_at": item.fulfilled_at, "rejection_reason": item.rejection_reason,
        "candidate": None if candidate is None else {"id": candidate.id, "candidate_code": candidate.candidate_code, "name": candidate.name,
                                                    "email": candidate.email, "anonymised": candidate.anonymised_at is not None},
        "open_applications": open_applications or 0, "held": bool(is_held),
    }  # fmt: skip


async def queue(db: AsyncSession, state: str) -> list[dict]:
    """Open requests oldest first (the order to work them); decided ones newest first, the last 100."""
    stmt = _queue_stmt()
    if state == "open":
        stmt = stmt.where(DataSubjectRequest.status == "in_progress").order_by(DataSubjectRequest.created_at, DataSubjectRequest.id)
    else:
        stmt = stmt.where(DataSubjectRequest.status != "in_progress").order_by(DataSubjectRequest.fulfilled_at.desc().nulls_last(), DataSubjectRequest.id).limit(100)
    return [_row_out(*row) for row in (await db.execute(stmt)).all()]


async def decide(db: AsyncSession, actor: User, request_id: UUID, decision: str, reason: str | None) -> tuple[dict, list[str]]:
    """Lock order: the request, then the candidate (approve). Approve runs the anonymiser in this transaction; reject keeps the record."""
    if decision not in ("approve", "reject"):
        raise HTTPException(422, "decision must be 'approve' or 'reject'")
    item = await db.scalar(select(DataSubjectRequest).join(User, User.id == DataSubjectRequest.requesting_user_id)
                           .where(DataSubjectRequest.id == request_id, DataSubjectRequest.type == "delete", User.role == PORTAL_ROLE)
                           .with_for_update(of=DataSubjectRequest))  # fmt: skip
    if item is None:
        raise HTTPException(404, NOT_FOUND)
    if item.status != "in_progress":
        raise HTTPException(409, DECIDED)
    keys: list[str] = []
    if decision == "reject":
        reason = (reason or "").strip()
        if not reason:
            raise HTTPException(422, "Give the candidate a reason for keeping their data")
        if len(reason) > REASON_LIMIT:
            raise HTTPException(422, f"Keep the reason to {REASON_LIMIT} characters")
        item.status, item.rejection_reason = "rejected", reason
    else:
        candidate = await db.scalar(select(Candidate).where(Candidate.user_id == item.requesting_user_id).with_for_update())
        if candidate is not None and candidate.anonymised_at is None:
            if await held(db, candidate.id):
                raise HTTPException(409, HELD)
            keys = await anonymise(db, candidate, "request", actor.id)
        else:
            await _close_portal_account(db, item.requesting_user_id)  # no candidate record left: the account still goes
        item.status = "fulfilled"
    item.fulfilled_at, item.fulfilled_by_user_id = datetime.now(UTC), actor.id
    db.add(AuditLog(user_id=actor.id, action=f"candidate.erasure_{'approved' if decision == 'approve' else 'rejected'}", entity_type="data_subject_request",
                    entity_id=str(item.id), metadata_json={"files": len(keys)}))  # fmt: skip
    logger.info("candidate_erasure_decided", extra={"extra_fields": {"actor_id": str(actor.id), "request_id": str(item.id), "decision": decision}})
    row = (await db.execute(_queue_stmt().where(DataSubjectRequest.id == item.id))).first()
    return _row_out(*row), keys


# --- K8 retention ------------------------------------------------------------------------------------------------------------------------
async def _setting(db: AsyncSession, lock: bool = False) -> CandidateRetentionSetting | None:
    return await db.get(CandidateRetentionSetting, 1, with_for_update=lock or None)


def _due(months: int, now: datetime):
    """External and portal candidates (never a student's) whose last activity is older than `months`, not held, no open application."""
    cutoff = now - timedelta(days=30 * months)
    last_application = select(func.max(JobApplication.updated_at)).where(JobApplication.candidate_id == Candidate.id).scalar_subquery()
    last_website = select(func.max(CareerApplication.created_at)).where(CareerApplication.candidate_id == Candidate.id).scalar_subquery()
    open_application = (select(JobApplication.id).where(JobApplication.candidate_id == Candidate.id, JobApplication.status.notin_(CLOSED_APPLICATIONS))
                        .exists())  # fmt: skip
    student = select(User.id).where(User.id == Candidate.user_id, User.role != PORTAL_ROLE).exists()
    return (Candidate.anonymised_at.is_(None), Candidate.merged_into_id.is_(None), ~student, ~open_application, ~_offer_in_progress(),
            func.greatest(Candidate.updated_at, func.coalesce(last_application, Candidate.updated_at), func.coalesce(last_website, Candidate.updated_at)) < cutoff)  # fmt: skip


async def retention_out(db: AsyncSession, user: User) -> dict:
    row = await _setting(db)
    months = row.months if row else None
    due = await db.scalar(select(func.count()).select_from(Candidate).where(*_due(months, datetime.now(UTC)))) if months else 0
    return {"months": months, "range": list(MONTHS_RANGE), "due_now": due or 0, "last_run_at": row.last_run_at if row else None,
            "last_run_count": row.last_run_count if row else None, "can_edit": user.role == "super_admin"}  # fmt: skip


async def save_retention(db: AsyncSession, actor: User, months) -> None:
    if actor.role != "super_admin":
        raise HTTPException(403, "Only a super admin can change the retention rule")
    if months is not None and (isinstance(months, bool) or not isinstance(months, int) or not MONTHS_RANGE[0] <= months <= MONTHS_RANGE[1]):
        raise HTTPException(422, PERIOD)
    row = await _setting(db, lock=True)
    if row is None:
        row = CandidateRetentionSetting(id=1)
        db.add(row)
    before = row.months
    row.months, row.updated_by_user_id = months, actor.id
    db.add(AuditLog(user_id=actor.id, action="candidate.retention_settings", entity_type="candidate_retention_settings", entity_id="1",
                    metadata_json={"from": before, "to": months}))  # fmt: skip


async def sweep(db: AsyncSession, *, now: datetime | None = None, batch: int = BATCH, max_batches: int = MAX_BATCHES) -> int:
    """The beat entry's body: off without a period. Batches of `batch` (SKIP LOCKED, so a candidate being edited waits for tomorrow),
    each committed with its files purged; one audit row per run with the count."""
    row = await _setting(db)
    if row is None or row.months is None:
        return 0
    now, total, months = now or datetime.now(UTC), 0, row.months  # captured: each commit expires `row`
    for _ in range(max_batches):
        rows = (await db.scalars(select(Candidate).where(*_due(months, now)).order_by(Candidate.id).limit(batch).with_for_update(skip_locked=True))).all()
        keys: list[str] = []
        for candidate in rows:
            keys += await anonymise(db, candidate, "retention", None)
        await db.commit()
        purge_files(keys)
        total += len(rows)
        if len(rows) < batch:
            break
    row = await _setting(db, lock=True)
    row.last_run_at, row.last_run_count = now, total
    db.add(AuditLog(user_id=None, action="candidate.retention_run", entity_type="candidate_retention_settings", entity_id="1",
                    metadata_json={"months": months, "anonymised": total}))  # fmt: skip
    await db.commit()
    logger.info("candidate_retention_run", extra={"extra_fields": {"months": months, "anonymised": total}})
    return total


async def run_retention() -> dict[str, int]:
    from app.core.database import SessionLocal

    async with SessionLocal() as db:
        return {"anonymised": await sweep(db)}


# --- K9 staff leaving --------------------------------------------------------------------------------------------------------------------
async def release_on_deactivation(db: AsyncSession, actor: User, user: User) -> int:
    """The deactivated user stops being a placement-officer owner or collaborator anywhere (history + audit each); the candidate-access
    roles whose session did not already end get a new `session_version`. Returns how many candidates changed."""
    officer_of = (await db.scalars(select(Candidate).where(Candidate.placement_officer_user_id == user.id).order_by(Candidate.id).with_for_update())).all()
    collaborations = (await db.scalars(select(CandidateCollaborator.candidate_id).where(CandidateCollaborator.user_id == user.id))).all()
    for candidate in officer_of:
        ownership.record(db, actor, candidate.id, "placement_officer", user.id, None, "reassign")
        candidate.placement_officer_user_id = None
    for candidate_id in collaborations:
        ownership.record(db, actor, candidate_id, "collaborator_removed", user.id, None, "reassign")
    await db.execute(delete(CandidateCollaborator).where(CandidateCollaborator.user_id == user.id))
    for candidate_id in {*(c.id for c in officer_of), *collaborations}:
        db.add(AuditLog(user_id=actor.id, action="candidate.assign", entity_type="candidates", entity_id=str(candidate_id),
                        metadata_json={"reason": "deactivated", "released_user_id": str(user.id)}))  # fmt: skip
    if user.role in SESSION_ROLES:
        user.session_version += 1
    return len({*(c.id for c in officer_of), *collaborations})
