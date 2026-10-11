"""rec-038 test builders: one fixture "world" for the recruiter CRM permission matrix (spec
docs/superpowers/specs/2026-10-11-rec-038-permission-matrix-design.md, RM2/RM5). Users are inserted directly and signed in with a minted
session cookie (no bcrypt round); records are inserted directly with the fields their own items' tests use. Every value is unique per
call: the test database is shared and never truncated."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import (
    BdmProfile,
    Candidate,
    Company,
    CompanyContact,
    EmployerProfile,
    Job,
    JobApplication,
    RecCandidateSource,
    RecruiterProfile,
    User,
)
from app.services import candidates as candidate_svc
from app.services.applications import candidate_for_student
from tests.tel026_helpers import headers

__all__ = ["PDF", "ROLES", "R", "Row", "add", "allow", "core", "headers", "make_candidate", "make_job", "now", "tag"]

# Who calls (RM2). `rec` owns the world's records and reports to `mgr`; `rec_out` / `mgr_out` are the same roles on another team; `bdm` is
# the company's assigned BDM (R10) and `bdm_out` any other BDM; `employer` is the company's employer user; `student` an opted-in IT student.
ROLES = ("rec", "rec_out", "mgr", "mgr_out", "super", "it_admin", "ovs_admin", "hr", "bdm", "bdm_out", "employer", "student", "anon")
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@dataclass
class Row:
    method: str
    path: str
    body: object = None  # a dict / callable(world) -> dict, sent as JSON
    form: object = None  # callable(world) -> (data, files), sent as multipart (with an Idempotency-Key)
    cells: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.method.upper()} {self.path}"

    def expected(self, role: str) -> int:
        """RM3: a cell not listed is refused -- 403 signed in, 401 signed out."""
        return self.cells.get(role, 401 if role == "anon" else 403)


def R(method: str, path: str, body=None, *, form=None, **cells) -> Row:
    return Row(method, path, body, form, cells)


def allow(status: int, *roles: str) -> dict:
    return dict.fromkeys(roles, status)


def tag(label: str = "") -> str:
    return f"{label}{uuid.uuid4().hex[:8]}"


def now() -> datetime:
    return datetime.now(UTC)


async def add(db, row):
    db.add(row)
    await db.flush()
    return row


async def _user(db, role: str, division: str) -> User:
    return await add(db, User(email=f"{tag('r38-')}@example.local", password_hash="!", full_name=f"{role} {tag()}", role=role, division=division,
                              active=True, email_verified=True, phone="+91 98765 43210"))  # fmt: skip


async def _recruiter(db, manager: User) -> User:
    user = await _user(db, "placement_team", "it")
    await add(db, RecruiterProfile(user_id=user.id, employee_id=tag("E38-"), reporting_manager_user_id=manager.id))
    return user


async def _bdm(db, manager: User) -> User:
    user = await _user(db, "bdm", "it")
    await add(db, BdmProfile(user_id=user.id, bdm_type="college", employee_id=tag("B38-"), reporting_manager_user_id=manager.id))
    return user


async def make_candidate(db, creator: User, **fields) -> Candidate:
    source = await db.scalar(select(RecCandidateSource).where(func.lower(RecCandidateSource.name) == "referral"))
    return await add(db, Candidate(candidate_code=await candidate_svc.next_code(db), source_id=source.id, created_by_user_id=creator.id,
                                   name=f"Rahul {tag()}", email=f"{tag('c38-')}@example.com", preferred_locations=[], opted_in=True, **fields))  # fmt: skip


async def make_job(db, company: Company, recruiter: User) -> Job:
    return await add(db, Job(company_id=company.id, title=f"Java {tag()}", location="Pune", description="Backend role", skills=[], status="sourcing",
                             assigned_recruiter_user_id=recruiter.id, created_by_user_id=recruiter.id))  # fmt: skip


async def core(client, db) -> dict:
    """The users by matrix role and the core records every group builds on. `rec` is the assigned recruiter of `company` (whose BDM is `bdm`
    and whose employer user is `employer`), of `requirement` and of `application` (the external `candidate` on it). The `*_out` roles
    hold nothing of this world, so each of its records is out of their scope."""
    mgr, mgr_out = await _user(db, "placement_manager", "global"), await _user(db, "placement_manager", "global")
    rec, rec2, rec_out = await _recruiter(db, mgr), await _recruiter(db, mgr), await _recruiter(db, mgr_out)
    bdm_mgr = await _user(db, "bdm_manager", "global")
    bdm, bdm_out = await _bdm(db, bdm_mgr), await _bdm(db, bdm_mgr)
    users = {
        "rec": rec, "rec2": rec2, "rec_out": rec_out, "mgr": mgr, "mgr_out": mgr_out, "super": await _user(db, "super_admin", "global"),
        "it_admin": await _user(db, "it_admin", "it"), "ovs_admin": await _user(db, "overseas_admin", "overseas"), "hr": await _user(db, "hr_team", "it"),
        "bdm": bdm, "bdm_out": bdm_out, "employer": await _user(db, "employer", "it"), "student": await _user(db, "it_student", "it"),
    }  # fmt: skip
    company = await add(db, Company(name=f"R38 Co {tag()}", assigned_recruiter_user_id=rec.id, assigned_bdm_user_id=bdm.id, created_by_user_id=rec.id))
    await add(db, EmployerProfile(user_id=users["employer"].id, company_id=company.id, registration_status=None))
    contact = await add(db, CompanyContact(company_id=company.id, name=f"Anita {tag()}", email=f"{tag('k38-')}@example.com", mobile="+91 90000 11111",
                                           is_primary=True))  # fmt: skip
    requirement = await make_job(db, company, rec)
    candidate = await make_candidate(db, rec)
    application = await add(db, JobApplication(job_id=requirement.id, candidate_id=candidate.id, added_by_user_id=rec.id, status="sourced"))
    student_candidate = await candidate_for_student(db, users["student"])
    student_candidate.opted_in = True
    await db.commit()
    return {
        "users": users, "today": now().date().isoformat(), "tomorrow": (now() + timedelta(days=1)).date().isoformat(),
        "company": str(company.id), "contact": str(contact.id), "requirement": str(requirement.id), "candidate": str(candidate.id),
        "application": str(application.id), "student_candidate": str(student_candidate.id), **{f"{k}_id": str(u.id) for k, u in users.items()},
    }  # fmt: skip
