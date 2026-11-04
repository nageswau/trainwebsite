"""hrc-023 (DEC-SCOPE-389, spec docs/superpowers/specs/2026-11-04-hrc-023-website-registration-intake-design.md): the public website's
front door to the recruiter pool. A job application creates -- or matches by exact email -- one candidate with source Website and the
visit's UTM (W1/W3), with the consent shown on the form (W4); the registration form's UTM reaches the candidate hrc-022 creates on
verification (W2, `candidate_portal`).

The email of a public form is not verified, so a match only LINKS the application: no field, consent or status of an existing candidate
changes (anti-goal). Never matched by phone. Functions only; nothing here commits -- the route owns the transaction. Logs and audit rows
carry ids and the IP, never a name, email or phone."""

import logging
import math
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Candidate, CandidateConsent, CareerApplication, Job, RecCandidateSource
from app.notifications.phone import normalise_phone
from app.services import candidate_duplicates as duplicates
from app.services import candidates as svc

logger = logging.getLogger("app.website_intake")

SOURCE = "Website"
DETAIL_APPLICATION = "Job application"
DETAIL_REGISTRATION = "Website registration"
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")
UTM_MAX = 100
MERGE_HOPS = 5  # a merged candidate is followed to its survivor; merges never chain this deep in practice

# W6: at most APPLY_MAX_PER_IP applications per client IP per rolling hour, counted from the `career.apply` audit rows.
APPLY_MAX_PER_IP = 10
APPLY_WINDOW = timedelta(hours=1)
APPLY_ACTION = "career.apply"
THROTTLED = "Too many applications from this network -- try again later"
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
LIMITS = {"full_name": 160, "email": 255, "phone": 40, "resume_url": 500, "cover_note": 5000}
LABELS = {"full_name": "Full name", "email": "Email", "phone": "Phone", "resume_url": "Resume", "cover_note": "Cover note"}


def clean_utm(raw) -> dict | None:
    """W1: the five standard keys only, trimmed and capped; anything else is dropped, never an error. None when nothing is left."""
    if not isinstance(raw, dict):
        return None
    kept = {key: value.strip()[:UTM_MAX] for key in UTM_KEYS if isinstance(value := raw.get(key), str) and value.strip()}
    return kept or None


def clean_application(payload: dict) -> dict:
    """The apply form's fields, checked against the columns (a 422 instead of a database error). Required fields are the route's."""
    fields = {key: (str(payload[key]).strip() if payload.get(key) is not None else None) for key in LIMITS}
    for key, limit in LIMITS.items():
        if fields[key] and len(fields[key]) > limit:
            raise HTTPException(422, f"{LABELS[key]} must be at most {limit} characters")
    fields["email"] = (fields["email"] or "").lower()
    if not EMAIL.match(fields["email"]):
        raise HTTPException(422, "Enter a valid email address")
    fields["phone"] = fields["phone"] or None
    if fields["phone"] and normalise_phone(fields["phone"]) is None:
        raise HTTPException(422, "Enter a valid mobile number")
    return fields


async def source_id(db: AsyncSession, name: str = SOURCE):
    """The catalogue value, created on first use (the hrc-022 idiom); matched case-insensitively, active or not."""
    found = await db.scalar(select(RecCandidateSource.id).where(func.lower(RecCandidateSource.name) == name.lower()))
    if found is None:
        source = RecCandidateSource(name=name)
        db.add(source)
        await db.flush()
        found = source.id
    return found


async def apply_wait_seconds(db: AsyncSession, ip: str) -> int:
    newest = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.action == APPLY_ACTION, AuditLog.created_at > datetime.now(UTC) - APPLY_WINDOW, AuditLog.metadata_json["ip"].as_string() == ip)
            .order_by(AuditLog.created_at.desc())
            .limit(APPLY_MAX_PER_IP)
        )
    ).all()
    if len(newest) < APPLY_MAX_PER_IP:
        return 0
    remaining = (newest[-1] + APPLY_WINDOW - datetime.now(UTC)).total_seconds()
    return min(int(APPLY_WINDOW.total_seconds()), max(1, math.ceil(remaining)))


async def _by_email(db: AsyncSession, email: str) -> Candidate | None:
    candidate = await db.scalar(select(Candidate).where(func.lower(Candidate.email) == email))
    for _ in range(MERGE_HOPS):
        if candidate is None or candidate.merged_into_id is None:
            break
        candidate = await db.get(Candidate, candidate.merged_into_id)
    return candidate


async def _create(db: AsyncSession, *, name: str, email: str, phone: str | None, utm: dict | None, consent_version: str | None, ip: str) -> Candidate:
    mobile_key = normalise_phone(phone) if phone else None
    if mobile_key and await db.scalar(select(Candidate.id).where(Candidate.mobile_normalized == mobile_key)):
        mobile_key = None  # W3: another candidate holds it (unique); it stays on the application, and phones never match
    candidate = Candidate(candidate_code=await svc.next_code(db), name=name[:160], email=email, mobile=phone if mobile_key else None,
                          mobile_normalized=mobile_key, preferred_locations=[], source_id=await source_id(db), source_detail=DETAIL_APPLICATION,
                          utm=utm, opted_in=consent_version is not None)  # fmt: skip
    db.add(candidate)
    await db.flush()
    if consent_version is not None:
        db.add(CandidateConsent(candidate_id=candidate.id, user_id=None, action="opt_in", consent_version=consent_version, ip_address=ip))
    db.add(AuditLog(user_id=None, action="candidate.create", entity_type="candidates", entity_id=str(candidate.id), metadata_json={"via": "website"}))
    await duplicates.detect(db, candidate.id)  # hrc-014 D2: probable matches go to the review queue
    return candidate


async def match_or_create(db: AsyncSession, *, name: str, email: str, phone: str | None, utm: dict | None, consent_version: str | None,
                          ip: str) -> tuple[Candidate, bool]:
    """W3/W5: the person's candidate and whether it was created. The email lock serialises two submissions of one person; a path that does
    not take it (a recruiter create, a portal verification) is caught at the unique index and the match is retried once."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"candidate:email:{email}"})
    if existing := await _by_email(db, email):
        return existing, False
    try:
        async with db.begin_nested():
            return await _create(db, name=name, email=email, phone=phone, utm=utm, consent_version=consent_version, ip=ip), True
    except IntegrityError:
        if existing := await _by_email(db, email):
            return existing, False
        async with db.begin_nested():  # the mobile was taken meanwhile: create without it
            return await _create(db, name=name, email=email, phone=None, utm=utm, consent_version=consent_version, ip=ip), True


async def apply(db: AsyncSession, job: Job, fields: dict, *, utm: dict | None, consent_version: str | None, ip: str) -> CareerApplication:
    candidate, created = await match_or_create(db, name=fields["full_name"], email=fields["email"], phone=fields["phone"], utm=utm,
                                               consent_version=consent_version, ip=ip)  # fmt: skip
    item = CareerApplication(job_id=job.id, full_name=fields["full_name"], email=fields["email"], phone=fields["phone"], resume_url=fields["resume_url"],
                             cover_note=fields["cover_note"], status="submitted", tracking_code=tracking_code(), candidate_id=candidate.id, utm=utm,
                             consent_version=consent_version, consented_at=datetime.now(UTC) if consent_version else None)  # fmt: skip
    db.add(item)
    await db.flush()
    outcome = "created" if created else "matched"
    db.add(AuditLog(user_id=None, action=APPLY_ACTION, entity_type="career_applications", entity_id=str(item.id),
                    metadata_json={"ip": ip, "candidate_id": str(candidate.id), "outcome": outcome}))  # fmt: skip
    logger.info("website_application", extra={"extra_fields": {"application_id": str(item.id), "candidate_id": str(candidate.id), "outcome": outcome}})
    return item


def tracking_code() -> str:
    return "EDU-CAREER-" + secrets.token_hex(5).upper()

