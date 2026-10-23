"""ccrm-012 (DEC-SCOPE-246 QS1-QS5): GET /counselor/search -- one box across the overseas counselor's own leads, students and applications."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AuditLog
from app.services import counselor_search
from tests.agn001_helpers import client_for, mk_user
from tests.ccrm012_helpers import SEARCH, search_world


@pytest_asyncio.fixture
async def world(db_session):
    return await search_world(db_session)


async def _search(c, q):
    r = await c.get(SEARCH, params={"q": q})
    assert r.status_code == 200, r.text
    data = r.json()
    return data, {group: {str(i["id"]) for i in data[group]["items"]} for group in ("leads", "students", "applications")}


@pytest.mark.asyncio
async def test_finds_each_entity_by_name_email_phone_and_code(world):
    async with client_for(world["a"].email) as c:
        _, hits = await _search(c, f"Zara Quill {world['tag']}")
        assert hits["students"] == {str(world["s1"].id)} and hits["applications"] == {str(world["app1"].id)}
        _, hits = await _search(c, world["s1"].email.upper())
        assert hits["students"] == {str(world["s1"].id)}
        _, hits = await _search(c, "98765-43210")  # phone, any separators
        assert hits["students"] == {str(world["s1"].id)} and hits["applications"] == {str(world["app1"].id)}
        _, hits = await _search(c, world["s1"].student_code.lower())
        assert hits["students"] == {str(world["s1"].id)}
        _, hits = await _search(c, world["app2"].application_code)
        assert hits["applications"] == {str(world["app2"].id)}
        _, hits = await _search(c, world["lead1"].lead_code)
        assert hits["leads"] == {str(world["lead1"].id)}
        _, hits = await _search(c, f"harper.{world['tag']}")
        assert hits["leads"] == {str(world["lead1"].id)}
        _, hits = await _search(c, "+91 98450 11223")
        assert hits["leads"] == {str(world["lead1"].id)}
        _, hits = await _search(c, f"Linked Lia {world['tag']}")  # a csc-001 linked student with no application
        assert hits["students"] == {str(world["linked"].id)} and hits["applications"] == set()


@pytest.mark.asyncio
async def test_another_counselors_student_phone_returns_nothing(world):  # backlog acceptance
    async with client_for(world["a"].email) as c:
        data, hits = await _search(c, "91234 56789")
        assert hits == {"leads": set(), "students": set(), "applications": set()}
        _, hits = await _search(c, "98450 11999")  # counselor B's lead
        assert hits["leads"] == set()
        _, hits = await _search(c, f"Other Ozzy {world['tag']}")
        assert hits["students"] == set() and hits["applications"] == set()


@pytest.mark.asyncio
async def test_items_carry_labels_and_links(world):
    async with client_for(world["a"].email) as c:
        data, _ = await _search(c, f"Zara Quill {world['tag']}")
    student = data["students"]["items"][0]
    assert student["label"] == world["s1"].full_name and student["code"] == world["s1"].student_code
    assert student["href"] == f"/overseas/counselor/students/{world['s1'].id}/notes"
    app = data["applications"]["items"][0]
    assert app["code"] == world["app1"].application_code and app["label"] == world["s1"].full_name
    assert world["uk"].name in app["detail"] and app["href"] == "/overseas/counselor/applications"
    assert data["students"]["more"] is False and data["q"] == f"Zara Quill {world['tag']}"


@pytest.mark.asyncio
async def test_lead_items_link_to_the_lead(world):
    async with client_for(world["a"].email) as c:
        data, _ = await _search(c, world["lead1"].lead_code)
    lead = data["leads"]["items"][0]
    assert (lead["code"], lead["href"]) == (world["lead1"].lead_code, f"/overseas/counselor/leads/{world['lead1'].id}")


@pytest.mark.asyncio
async def test_wildcards_are_literal(world):
    async with client_for(world["a"].email) as c:
        _, hits = await _search(c, "%%%")
    assert hits == {"leads": set(), "students": set(), "applications": set()}


@pytest.mark.asyncio
@pytest.mark.parametrize("q", ["ab", "  ab  ", "x" * 101])
async def test_query_length_is_enforced(world, q):
    async with client_for(world["a"].email) as c:
        r = await c.get(SEARCH, params={"q": q})
    assert r.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("overseas_admin", "overseas"), ("counselor", "it"), ("agent", "overseas"), ("overseas_student", "overseas")])
async def test_only_an_overseas_counselor_may_search(db_session, role, division):
    user = await mk_user(db_session, role=role, division=division)
    async with client_for(user.email, division) as c:
        r = await c.get(SEARCH, params={"q": "anyone"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_each_search_is_audited_without_the_text_and_throttled(db_session, world):
    async with client_for(world["a"].email) as c:
        await _search(c, f"Zara Quill {world['tag']}")
        rows = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == world["a"].id, AuditLog.action == counselor_search.AUDIT_ACTION))).all()
        assert len(rows) == 1 and rows[0].metadata_json == {"leads": 0, "students": 1, "applications": 1}
        db_session.add_all(AuditLog(user_id=world["a"].id, action=counselor_search.AUDIT_ACTION, entity_type="search", outcome="searched", metadata_json={},
                                    created_at=datetime.now(UTC)) for _ in range(counselor_search.RATE_LIMIT))
        await db_session.commit()
        r = await c.get(SEARCH, params={"q": "anyone"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
