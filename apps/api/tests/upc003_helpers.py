"""upc-003 test builders, on top of upc-001's. Every value is unique per call: the test database is shared and never truncated."""

import uuid

from sqlalchemy import select

from app.models import Country, OverseasApplication, PartnershipProfile, User
from tests.upc001_helpers import as_role, emp, login, make_head, make_user

__all__ = ["BASE", "as_role", "catalogue_country", "create", "internal_country", "login", "make_application", "make_head", "make_pm",
           "make_user", "payload", "url"]

BASE = "/api/v1/partnership/universities"


def url(university_id, action: str | None = None) -> str:
    return f"{BASE}/{university_id}" + (f"/{action}" if action else "")


async def catalogue_country(db) -> Country:
    return await db.scalar(select(Country).where(Country.iso2 == "GB"))


async def internal_country(db) -> Country:
    return await db.scalar(select(Country).where(Country.iso2 == "JP"))


async def make_pm(db, head: User, *, active: bool = True, name: str | None = None) -> User:
    manager = await make_user(db, "partnership_manager", "overseas", active=active, name=name)
    db.add(PartnershipProfile(user_id=manager.id, employee_id=emp(), reporting_head_user_id=head.id))
    await db.commit()
    return manager


def payload(country_id, **overrides) -> dict:
    body = {
        "name": f"ABC University {uuid.uuid4().hex[:8]}", "country_id": str(country_id), "city": "London", "institution_type": "university",
        "ownership_type": "public", "state_region": "Greater London", "website": "abc.ac.uk", "course_levels": ["UG", "PG"],
        "popular_programs": ["Business", "Engineering"], "international_office": "intl@abc.ac.uk, +44 20 0000 0000",
        "existing_relationship": "new", "priority": "A", "partnership_potential": "high",
        "rankings": [{"system": "QS", "year": 2026, "rank": "145"}, {"system": "Other", "other_name": "Guardian", "year": 2025, "rank": "201-250"}],
    }
    body.update(overrides)
    return body


async def create(client, country_id, **overrides) -> dict:
    response = await client.post(BASE, json=payload(country_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()["university"]


async def make_application(db, university_id) -> OverseasApplication:
    student = await make_user(db, "overseas_student", "overseas")
    row = OverseasApplication(student_id=student.id, university_id=university_id, intake="Sep 2027")
    db.add(row)
    await db.commit()
    return row
