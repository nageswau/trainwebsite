"""ccrm-012 (DEC-SCOPE-246 QS1-QS5): the overseas counselor's quick search -- one box across their own leads (tel-018 scope), students
(csc-001 visible students) and applications (assigned to them). Name, email and code match as a literal, case-insensitive substring; a
phone-shaped search also matches the digits of the phone, whatever its separators. Each group is capped; nothing outside the scope is
read, so another counselor's record never matches.

Every search writes one audit row (result counts only -- never the search text) and the rows are the 30-a-minute budget (the lookups
`purpose=link` precedent)."""

import logging
import math
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentStudent, AuditLog, Enquiry, OverseasApplication, University, User
from app.services import counselor_students, lead_handover
from app.services.agent_applications import OWNER_NAME, owned, with_owner

logger = logging.getLogger("app.counselor_search")

MIN_CHARS, MAX_CHARS = 3, 100
GROUP_LIMIT = 10
RATE_LIMIT, RATE_WINDOW = 30, timedelta(minutes=1)
AUDIT_ACTION = "counselor.search"
OVERSEAS_COUNSELOR_ONLY = "Only an overseas counselor can search here"
TOO_SHORT = f"Type at least {MIN_CHARS} characters"
TOO_LONG = f"Use at most {MAX_CHARS} characters"
_PHONE_SHAPED = re.compile(r"[\d\s+\-().]+")


def term(q: str) -> str:
    text = q.strip()
    if len(text) < MIN_CHARS:
        raise HTTPException(422, TOO_SHORT)
    if len(text) > MAX_CHARS:
        raise HTTPException(422, TOO_LONG)
    return text


def _digits_pattern(text: str) -> str | None:
    """`%<digits>%` when the search looks like a phone number with at least three digits, else None. Past ten digits only the last ten
    count (tel-018 T20's rule), so a typed country code still finds a number stored without one."""
    digits = re.sub(r"\D", "", text)[-10:]
    return f"%{digits}%" if _PHONE_SHAPED.fullmatch(text) and len(digits) >= MIN_CHARS else None


def _matches(pattern: str, digits: str | None, text_columns, phone_columns):
    clauses = [c.ilike(pattern, escape="\\") for c in text_columns]
    if digits:
        clauses += [func.regexp_replace(c, r"\D", "", "g").like(digits) for c in phone_columns]
    return or_(*clauses)


async def _wait_seconds(db: AsyncSession, user: User, action: str = AUDIT_ACTION) -> int:
    """Seconds before `user` may search again (0: now), counted from their `action` audit rows; nehn-041 counts its own action."""
    now = datetime.now(UTC)
    recent = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.user_id == user.id, AuditLog.action == action, AuditLog.created_at > now - RATE_WINDOW)
            .order_by(AuditLog.created_at.desc())
            .limit(RATE_LIMIT)
        )
    ).all()
    if len(recent) < RATE_LIMIT:
        return 0
    return max(1, math.ceil((recent[-1] + RATE_WINDOW - now).total_seconds()))


def _group(items: list[dict]) -> dict:
    return {"items": items[:GROUP_LIMIT], "more": len(items) > GROUP_LIMIT}


async def search(db: AsyncSession, user: User, text: str, pattern: str) -> dict:
    """`pattern` is `text` as an escaped `%…%` ILIKE pattern. The caller has checked the role (an overseas counselor)."""
    wait = await _wait_seconds(db, user)
    if wait:
        logger.warning("counselor_search_throttled", extra={"extra_fields": {"actor_id": str(user.id), "wait_seconds": wait}})
        raise HTTPException(429, f"Too many searches; try again in {wait} seconds", headers={"Retry-After": str(wait)})
    digits = _digits_pattern(text)
    base = "/overseas/counselor"
    leads = (
        await db.scalars(
            select(Enquiry)
            .where(*lead_handover.counselor_scope(user), _matches(pattern, digits, (Enquiry.name, Enquiry.email, Enquiry.lead_code), (Enquiry.phone,)))
            .order_by(Enquiry.created_at.desc(), Enquiry.id)
            .limit(GROUP_LIMIT + 1)
        )
    ).all()
    students = (
        await db.scalars(
            select(User)
            .where(User.role == "overseas_student", User.id.in_(counselor_students.visible_student_ids(user)),
                   _matches(pattern, digits, (User.full_name, User.email, User.student_code), (User.phone,)))
            .order_by(User.full_name, User.id)
            .limit(GROUP_LIMIT + 1)
        )
    ).all()
    applications = owned(
        (
            await db.execute(
                with_owner(select(OverseasApplication, University).join(University, University.id == OverseasApplication.university_id))
                .where(OverseasApplication.counselor_id == user.id,
                       _matches(pattern, digits, (OverseasApplication.application_code, OWNER_NAME, User.email, AgentStudent.email), (User.phone, AgentStudent.phone)))
                .order_by(OverseasApplication.updated_at.desc(), OverseasApplication.id)
                .limit(GROUP_LIMIT + 1)
            )
        ).all()
    )
    result = {
        "q": text,
        "leads": _group([{"id": e.id, "code": e.lead_code, "label": e.name, "detail": e.email or e.phone, "href": f"{base}/leads/{e.id}"} for e in leads]),
        "students": _group([{"id": s.id, "code": s.student_code, "label": s.full_name, "detail": s.email, "href": f"{base}/students/{s.id}/notes"} for s in students]),
        "applications": _group([
            # QA-01: no counselor application page yet, so the list opens narrowed to this application's university and intake
            {"id": a.id, "code": a.application_code, "label": owner.full_name, "detail": f"{u.name} · {a.intake}",
             "href": f"{base}/applications?{urlencode({'university': a.university_id, 'intake': a.intake})}"}
            for a, u, owner in applications
        ]),
    }
    counts = {group: len(result[group]["items"]) for group in ("leads", "students", "applications")}
    db.add(AuditLog(user_id=user.id, action=AUDIT_ACTION, entity_type="search", outcome="searched", metadata_json=counts))
    await db.commit()
    return result
