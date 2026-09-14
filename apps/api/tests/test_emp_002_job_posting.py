"""EMP-002 -- Job posting.

Net-new: no endpoint let the Employer role (EMP-001) post a job at all -- job creation
was Placement Team/HR Team/Admin-only (`POST /it/jobs`). Added a self-scoped
`POST/GET/PATCH /employer/jobs` family. `API_CONTRACT.md` §6 fixes the starting state to
"draft" -- whether it then needs staff `pending_review` before publishing is an open
mediation question, so no such gate is invented; the Employer publishes their own draft
by setting `status: "open"` themselves, the same "no invented approval gate" precedent
already established by `EMP-001`'s own `registration_status`.

Separately, found and fixed a real, confirmed `EMP-002-AC02` gap that predates this
feature: `GET /it/jobs/open`, `GET /public/jobs`, and both job-application endpoints only
ever checked `Job.status == "open"` -- a posting whose `closes_on` date had already
passed, but whose status the Employer never explicitly flipped, still showed (and was
still applicable to) as open everywhere. Fixed all four call sites to also check
`closes_on`.
"""

import datetime
import uuid

import pytest

from app.core.security import hash_password
from app.models import Job, User


def _register_payload(**overrides) -> dict:
    base = {
        "email": f"emp002-{uuid.uuid4().hex[:8]}@example.local",
        "password": "Sup3r-Secret-Pass!",
        "full_name": "Job Poster",
        "company_name": f"Acme Jobs {uuid.uuid4().hex[:6]}",
        "company_website": "https://acme.example.com",
    }
    base.update(overrides)
    return base


def _title(label: str) -> str:
    return f"{label} {uuid.uuid4().hex[:8]}"


async def _register_employer(client, **overrides) -> dict:
    response = await client.post("/api/v1/employer/register", json=_register_payload(**overrides))
    assert response.status_code == 200
    return response.json()


async def _create_student(db_session) -> User:
    student = User(
        email=f"emp002-student-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Test Student", role="it_student", division="it", active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_a_new_posting_starts_as_a_draft_not_visible_to_students(client, db_session):
    await _register_employer(client)
    title = _title("Backend Engineer")
    created = await client.post("/api/v1/employer/jobs", json={"title": title, "location": "Bengaluru", "skills": ["Python", "FastAPI"]})
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "draft"
    assert body["visible_to_students"] is False
    job_id = body["id"]

    student = await _create_student(db_session)
    await _login(client, student.email)
    open_jobs = await client.get("/api/v1/workflows/it/jobs/open")
    assert not any(j["title"] == title for j in open_jobs.json())
    public_jobs = await client.get("/api/v1/public/jobs")
    assert not any(j["title"] == title for j in public_jobs.json())
    apply_response = await client.post(f"/api/v1/workflows/it/jobs/{job_id}/apply", json={})
    assert apply_response.status_code == 404


@pytest.mark.asyncio
async def test_employer_publishes_their_own_draft_and_it_becomes_visible_to_students(client, db_session):
    await _register_employer(client)
    title = _title("Frontend Engineer")
    created = await client.post("/api/v1/employer/jobs", json={"title": title})
    job_id = created.json()["id"]

    published = await client.patch(f"/api/v1/employer/jobs/{job_id}", json={"status": "open"})
    assert published.status_code == 200
    assert published.json()["status"] == "open"
    assert published.json()["visible_to_students"] is True

    student = await _create_student(db_session)
    await _login(client, student.email)
    open_jobs = await client.get("/api/v1/workflows/it/jobs/open")
    assert any(j["title"] == title for j in open_jobs.json())
    public_jobs = await client.get("/api/v1/public/jobs")
    assert any(j["title"] == title for j in public_jobs.json())


@pytest.mark.asyncio
async def test_employer_only_sees_their_own_postings(client, db_session):
    await _register_employer(client)
    await client.post("/api/v1/employer/jobs", json={"title": "Mine"})

    await _register_employer(client)
    listing = await client.get("/api/v1/employer/jobs")
    assert listing.status_code == 200
    assert listing.json() == []


@pytest.mark.asyncio
async def test_a_published_job_past_its_closing_date_is_not_shown_as_open_even_if_never_closed(client, db_session):
    await _register_employer(client)
    title = _title("Expired Role")
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    created = await client.post("/api/v1/employer/jobs", json={"title": title, "closes_on": yesterday})
    job_id = created.json()["id"]

    published = await client.patch(f"/api/v1/employer/jobs/{job_id}", json={"status": "open"})
    assert published.json()["status"] == "open"  # never explicitly closed
    assert published.json()["visible_to_students"] is False

    student = await _create_student(db_session)
    await _login(client, student.email)

    open_jobs = await client.get("/api/v1/workflows/it/jobs/open")
    assert not any(j["title"] == title for j in open_jobs.json())

    apply_response = await client.post(f"/api/v1/workflows/it/jobs/{job_id}/apply", json={})
    assert apply_response.status_code == 404

    public_jobs = await client.get("/api/v1/public/jobs")
    assert not any(j["title"] == title for j in public_jobs.json())

    public_apply = await client.post(f"/api/v1/public/jobs/{job_id}/apply", json={"full_name": "X", "email": "x@example.local", "resume_url": "https://x.example.com/r.pdf"})
    assert public_apply.status_code == 404


@pytest.mark.asyncio
async def test_an_employer_cannot_update_another_employers_job_even_via_direct_id(client, db_session):
    await _register_employer(client)
    created = await client.post("/api/v1/employer/jobs", json={"title": "Not yours"})
    job_id = created.json()["id"]

    await _register_employer(client)
    response = await client.patch(f"/api/v1/employer/jobs/{job_id}", json={"status": "open"})
    assert response.status_code == 403

    job = await db_session.get(Job, job_id)
    await db_session.refresh(job)
    assert job.status == "draft"


@pytest.mark.asyncio
async def test_employer_can_close_their_own_published_job(client, db_session):
    await _register_employer(client)
    created = await client.post("/api/v1/employer/jobs", json={"title": "Will Close"})
    job_id = created.json()["id"]
    await client.patch(f"/api/v1/employer/jobs/{job_id}", json={"status": "open"})

    response = await client.patch(f"/api/v1/employer/jobs/{job_id}", json={"status": "closed"})
    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    assert response.json()["visible_to_students"] is False


@pytest.mark.asyncio
async def test_an_unsupported_status_value_is_rejected(client, db_session):
    await _register_employer(client)
    created = await client.post("/api/v1/employer/jobs", json={"title": "Test"})
    job_id = created.json()["id"]
    response = await client.patch(f"/api/v1/employer/jobs/{job_id}", json={"status": "filled"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_non_employer_role_is_rejected(client, db_session):
    student = await _create_student(db_session)
    await _login(client, student.email)
    response = await client.post("/api/v1/employer/jobs", json={"title": "Nope"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_job_posting_requires_authentication(client):
    response = await client.post("/api/v1/employer/jobs", json={"title": "Nope"})
    assert response.status_code == 401
