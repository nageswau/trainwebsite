"""upc-008 -- the §5 expected timeline on the university (spec §3; X1, MS8-MS10, Q-10)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.upc003_helpers import as_role, login, make_pm, make_user, url
from tests.upc007_helpers import owned_university

FULL = {
    "target_partnership_date": "2026-11-15",
    "expected_intake": "  January 2027 ",
    "expected_agreement_date": "2026-10-30",
    "expected_recruitment_start": "2026-12-01",
}


async def _patch(client, university_id, body: dict):
    return await client.patch(url(university_id, "expected"), json=body)


@pytest.mark.asyncio
async def test_a_new_university_has_no_expected_timeline_and_the_owner_may_edit_it(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    body = (await client.get(url(uni["id"]))).json()["university"]
    assert body["expected"] == {
        "target_partnership_date": None, "expected_month": None, "expected_quarter": None, "expected_intake": None,
        "expected_agreement_date": None, "expected_recruitment_start": None,
    }  # fmt: skip
    assert body["permissions"]["can_edit_timeline"] is True


@pytest.mark.asyncio
async def test_the_owner_records_the_targets_and_month_and_quarter_are_derived(client, db_session):
    """§5 L184-L194; Q-10 (MS8): month and quarter come from the target partnership date, calendar quarters."""
    _, _, uni = await owned_university(client, db_session)
    response = await _patch(client, uni["id"], FULL)
    assert response.status_code == 200, response.text
    expected = response.json()["university"]["expected"]
    assert expected == {
        "target_partnership_date": "2026-11-15", "expected_month": "2026-11", "expected_quarter": "2026-Q4", "expected_intake": "January 2027",
        "expected_agreement_date": "2026-10-30", "expected_recruitment_start": "2026-12-01",
    }  # fmt: skip
    assert (await client.get(url(uni["id"]))).json()["university"]["expected"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(("day", "quarter"), [("2027-01-01", "2027-Q1"), ("2027-03-31", "2027-Q1"), ("2027-04-01", "2027-Q2"), ("2027-09-30", "2027-Q3")])
async def test_calendar_quarter_boundaries(client, db_session, day, quarter):
    _, _, uni = await owned_university(client, db_session)
    expected = (await _patch(client, uni["id"], {"target_partnership_date": day})).json()["university"]["expected"]
    assert expected["expected_quarter"] == quarter and expected["expected_month"] == day[:7]


@pytest.mark.asyncio
async def test_only_the_fields_sent_change_null_clears_and_blank_intake_is_null(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    await _patch(client, uni["id"], FULL)
    expected = (await _patch(client, uni["id"], {"target_partnership_date": None, "expected_intake": "   "})).json()["university"]["expected"]
    assert expected["target_partnership_date"] is None and expected["expected_month"] is None and expected["expected_quarter"] is None
    assert expected["expected_intake"] is None and expected["expected_agreement_date"] == "2026-10-30"


@pytest.mark.asyncio
async def test_the_audit_names_the_fields_only(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    await _patch(client, uni["id"], FULL)
    await _patch(client, uni["id"], FULL)  # no change: no second audit row
    db_session.expire_all()
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == uni["id"], AuditLog.action == "university.expected_updated"))).all()
    assert [r.metadata_json for r in rows] == [{"fields": ["expected_agreement_date", "expected_intake", "expected_recruitment_start", "target_partnership_date"]}]
    assert "January" not in str(rows[0].metadata_json)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"expected_month": "2026-11"}, {"expected_intake": "x" * 81}, {"target_partnership_date": "next month"}])
async def test_empty_extra_too_long_or_malformed_is_422(client, db_session, body):
    _, _, uni = await owned_university(client, db_session)
    assert (await _patch(client, uni["id"], body)).status_code == 422


@pytest.mark.asyncio
async def test_non_owner_manager_and_overseas_admin_are_403(client, db_session):
    head, _, uni = await owned_university(client, db_session)
    await login(client, await make_pm(db_session, head))
    assert (await _patch(client, uni["id"], FULL)).status_code == 403
    await as_role(client, db_session, "overseas_admin", "overseas")
    assert (await _patch(client, uni["id"], FULL)).status_code == 403
    body = (await client.get(url(uni["id"]))).json()["university"]
    assert body["permissions"]["can_edit_timeline"] is False and body["expected"]["target_partnership_date"] is None


@pytest.mark.asyncio
async def test_head_and_super_admin_may_edit_inactive_is_409_unknown_is_404(client, db_session):
    head, pm, uni = await owned_university(client, db_session)
    await login(client, head)
    assert (await _patch(client, uni["id"], {"expected_intake": "Sep 2027"})).status_code == 200
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await _patch(client, uni["id"], {"expected_intake": "Jan 2028"})).status_code == 200
    assert (await _patch(client, uuid.uuid4(), {"expected_intake": "Jan 2028"})).status_code == 404
    await login(client, head)
    assert (await client.post(url(uni["id"], "deactivate"), json={})).status_code == 200
    await login(client, pm)
    assert (await _patch(client, uni["id"], {"expected_intake": "Jan 2028"})).status_code == 409
