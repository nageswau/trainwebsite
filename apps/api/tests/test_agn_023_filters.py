"""AGN-023 AC16-AC18, AC13 shape -- Agency / Counsellor filters on the overseas Students and Applications lists (spec §3.3)."""

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from app.models import OverseasApplication
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import mk_application
from tests.agn023_helpers import ASSIGN, PORTAL, assign_world


@pytest_asyncio.fixture
async def world(db_session):
    w = await assign_world(db_session)
    async with client_for(w["admin"].email) as c:
        assert (await c.put(ASSIGN.format(w["app"].id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    w["other_app"] = await mk_application(db_session, agent=w["other"]["master"], university=w["university"], record=await mk_record(db_session, agent=w["other"]["master"], full_name=f"Other {uniq()}"))
    return w


async def _ids(c, role, section="applications", **params):
    r = await c.get(PORTAL.format(role, section), params=params)
    assert r.status_code == 200, r.text
    return r.json(), {str(row["id"]) for row in r.json()["rows"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["applications", "students"])
async def test_admin_filters_by_agency_and_counselor(world, section):  # AC16
    a, direct, other = str(world["app"].id), str(world["direct_app"].id), str(world["other_app"].id)
    async with client_for(world["admin"].email) as c:
        _, ids = await _ids(c, "admin", section, agency=str(world["org"].id))
        assert a in ids and other not in ids and direct not in ids
        _, ids = await _ids(c, "admin", section, agency="any")
        assert {a, other} <= ids and direct not in ids
        _, ids = await _ids(c, "admin", section, agency="none")
        assert direct in ids and a not in ids
        _, ids = await _ids(c, "admin", section, counselor=str(world["counselor"].id))
        assert a in ids and other not in ids
        _, ids = await _ids(c, "admin", section, agency="any", counselor="none")
        assert other in ids and a not in ids and direct not in ids


@pytest.mark.asyncio
async def test_admin_rows_and_options(world):  # AC15 data, AC16
    async with client_for(world["admin"].email) as c:
        data, _ = await _ids(c, "admin", agency=str(world["org"].id))
    row = next(r for r in data["rows"] if str(r["id"]) == str(world["app"].id))
    assert (row["is_agency"], row["agency"], row["counselor"], row["counselor_id"]) == (True, world["org"].name, world["counselor"].full_name, str(world["counselor"].id))
    assert {"key": "assign", "label": "", "type": "assign_counselor"} in data["columns"]
    assert data["filters"]["agency"] == str(world["org"].id) and data["filters"]["counselor"] is None
    assert {"value": str(world["org"].id), "label": world["org"].name} in data["filters"]["agencies"]
    labels = {o["value"]: o["label"] for o in data["filters"]["counselors"]}
    assert labels[str(world["inactive"].id)] == f"{world['inactive'].full_name} (inactive)"
    assert str(world["it_counselor"].id) not in labels


@pytest.mark.asyncio
async def test_a_counselor_filters_by_agency_within_their_own_caseload(world):  # AC17
    async with client_for(world["counselor"].email) as c:
        data, ids = await _ids(c, "counselor", agency=str(world["org"].id))
        assert ids == {str(world["app"].id)}
        assert [o["value"] for o in data["filters"]["agencies"]] == [str(world["org"].id)]  # never the other agency
        assert "counselors" not in data["filters"]
        row = data["rows"][0]
        assert (row["is_agency"], row["agency"]) == (True, world["org"].name) and "counselor_id" not in row
        _, ids = await _ids(c, "counselor", agency=str(world["other"]["org"].id))
        assert ids == set()
        r = await c.get(PORTAL.format("counselor", "applications"), params={"counselor": str(world["counselor"].id)})
    assert r.status_code == 422 and r.json()["detail"] == "Filter not available"


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "section", "params", "detail"), [
    ("admin", "applications", {"agency": "garbage"}, "Unknown filter value"),
    ("admin", "applications", {"agency": str(uuid.uuid4())}, "Unknown filter value"),
    ("admin", "applications", {"counselor": "any"}, "Unknown filter value"),
    ("admin", "dashboard", {"agency": "any"}, "Filter not available"),
    ("admin", "documents", {"counselor": "none"}, "Filter not available"),
])
async def test_bad_filters_are_refused(world, role, section, params, detail):  # AC18
    async with client_for(world["admin"].email) as c:
        r = await c.get(PORTAL.format(role, section), params=params)
    assert r.status_code == 422 and r.json()["detail"] == detail


@pytest.mark.asyncio
async def test_a_counselor_id_filter_must_name_an_overseas_counselor(world):  # AC18
    async with client_for(world["admin"].email) as c:
        r = await c.get(PORTAL.format("admin", "applications"), params={"counselor": str(world["it_counselor"].id)})
    assert r.status_code == 422 and r.json()["detail"] == "Unknown filter value"


@pytest.mark.asyncio
async def test_a_university_rep_gets_no_filters(db_session, world):  # AC18
    rep = await mk_user(db_session, role="university_rep", profile={"university_id": str(world["university"].id)})
    async with client_for(rep.email) as c:
        r = await c.get(PORTAL.format("university", "applications"), params={"agency": "any"})
        assert r.status_code == 422 and r.json()["detail"] == "Filter not available"
        plain = (await c.get(PORTAL.format("university", "applications"))).json()
    assert "filters" not in plain and all("counselor" not in row and "agency" not in row for row in plain["rows"])


@pytest.mark.asyncio
async def test_filters_apply_before_the_500_row_cap(db_session, world):  # AC16, Review Focus 5
    ctx = await mk_active_org(db_session, name=f"Old Agency {uniq()}")
    old = await mk_application(db_session, agent=ctx["master"], university=world["university"], record=await mk_record(db_session, agent=ctx["master"], full_name=f"Old {uniq()}"))
    old.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
    student = await mk_user(db_session, role="overseas_student")
    db_session.add_all(OverseasApplication(student_id=student.id, university_id=world["university"].id, status="enquiry", intake="Fall 2027") for _ in range(501))
    await db_session.commit()
    async with client_for(world["admin"].email) as c:
        _, unfiltered = await _ids(c, "admin")
        _, filtered = await _ids(c, "admin", agency=str(ctx["org"].id))
    assert str(old.id) not in unfiltered
    assert filtered == {str(old.id)}


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "section", "email_key"), [("admin", "admission-updates", "admin"), ("counselor", "admission-updates", "counselor"), ("admin", "offer-letters", "admin")])
async def test_other_sections_keep_their_original_payload(world, role, section, email_key):  # AC18: no filters advertised where they are refused
    async with client_for(world[email_key].email) as c:
        data, _ = await _ids(c, role, section)
    assert "filters" not in data
    assert [col["key"] for col in data["columns"]] == ["id", "student", "university", "reference", "status", "next_action"]
    assert all(not {"agency", "counselor", "counselor_id", "is_agency", "assign"} & row.keys() for row in data["rows"])


@pytest.mark.asyncio
async def test_a_university_rep_counselor_filter_is_refused(db_session, world):  # AC18
    rep = await mk_user(db_session, role="university_rep", profile={"university_id": str(world["university"].id)})
    async with client_for(rep.email) as c:
        r = await c.get(PORTAL.format("university", "applications"), params={"counselor": str(world["counselor"].id)})
    assert r.status_code == 422 and r.json()["detail"] == "Filter not available"


@pytest.mark.asyncio
@pytest.mark.parametrize("param", ["agency", "counselor"])
async def test_a_repeated_filter_parameter_is_refused(world, param):  # B7: never silently use one of two values
    other = str(world["org"].id) if param == "agency" else str(world["counselor"].id)
    async with client_for(world["admin"].email) as c:
        r = await c.get(PORTAL.format("admin", "applications") + f"?{param}={other}&{param}={other}")
    assert r.status_code == 422 and r.json()["detail"] == "Unknown filter value"


@pytest.mark.asyncio
async def test_a_repeated_counselor_filter_from_a_counselor_is_not_available(world):  # availability is checked before repetition
    async with client_for(world["counselor"].email) as c:
        r = await c.get(PORTAL.format("counselor", "applications") + "?counselor=x&counselor=y")
    assert r.status_code == 422 and r.json()["detail"] == "Filter not available"


@pytest.mark.asyncio
async def test_a_repeated_filter_on_a_non_filter_section_is_not_available(world):  # availability is checked before repetition
    async with client_for(world["admin"].email) as c:
        r = await c.get(PORTAL.format("admin", "admission-updates") + "?agency=any&agency=none")
    assert r.status_code == 422 and r.json()["detail"] == "Filter not available"


@pytest.mark.asyncio
async def test_a_repeated_filter_on_an_available_section_is_unknown_value(world):  # repetition comes second, only once the filter is available
    async with client_for(world["admin"].email) as c:
        r = await c.get(PORTAL.format("admin", "students") + "?agency=any&agency=none")
    assert r.status_code == 422 and r.json()["detail"] == "Unknown filter value"


@pytest.mark.asyncio
@pytest.mark.parametrize("section", ["applications", "students"])
async def test_a_counselor_filters_return_only_their_own_matching_rows(world, section):  # T15
    async with client_for(world["admin"].email) as c:
        assert (await c.put(ASSIGN.format(world["direct_app"].id), json={"counselor_id": str(world["counselor"].id)})).status_code == 200
        assert (await c.put(ASSIGN.format(world["other_app"].id), json={"counselor_id": str(world["counselor2"].id)})).status_code == 200
    a, direct, other = str(world["app"].id), str(world["direct_app"].id), str(world["other_app"].id)
    async with client_for(world["counselor"].email) as c:
        _, ids = await _ids(c, "counselor", section, agency=str(world["org"].id))
        assert ids == {a}
        _, ids = await _ids(c, "counselor", section, agency=str(world["other"]["org"].id))
        assert ids == set()  # the other agency's application is counselor2's, never this counselor's
        _, ids = await _ids(c, "counselor", section, agency="any")
        assert ids == {a}
        _, ids = await _ids(c, "counselor", section, agency="none")
        assert ids == {direct}
        assert other not in (await _ids(c, "counselor", section))[1]
