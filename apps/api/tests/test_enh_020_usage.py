"""ENH-020 -- entitlement usage for loan / scholarship assistance (spec §5, D8/D9/D12; AC13, AC14)."""

import pytest
from enh005_helpers import login, mk_school, mk_staff, move_student_directly

from app.api.school_analytics import SCORECARD_AREAS, UNTRACKED_OUTCOMES
from app.api.school_global_education import NOT_TRACKED
from app.api.schools import service_usage

CASES = "/api/v1/school/funding-records"


async def _open(client, student, support_type) -> dict:
    r = await client.post(CASES, json={"school_student_id": str(student.id), "support_type": support_type})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_usage_counts_distinct_students_per_creating_school(client, db_session):  # AC13, D8, D12
    a = await mk_school(db_session, label="E20U-A", students=3)
    b = await mk_school(db_session, label="E20U-B", admin=a["admin"], students=0)
    counselor = await mk_staff(db_session, a["school"], a["admin"], role="career_counselor")
    first, second, third = a["students"]
    await login(client, counselor.email)
    await _open(client, first, "education_loan")
    await _open(client, first, "funding_guidance")  # same student, another loan-family type: still one student
    closed = await _open(client, second, "financial_assistance")
    assert (await client.patch(f"{CASES}/{closed['id']}", json={"status": "closed", "closure_reason": "Withdrawn"})).status_code == 200
    await _open(client, third, "scholarship")
    await move_student_directly(db_session, third, b["school"])  # the delivered service stays with the creating school

    usage = await service_usage(db_session, [a["school"].id, b["school"].id])

    assert usage[a["school"].id]["loan_assistance"] == 2  # first + second (closed still counts)
    assert usage[a["school"].id]["scholarship_assistance"] == 1
    assert usage[b["school"].id]["loan_assistance"] == 0 and usage[b["school"].id]["scholarship_assistance"] == 0


@pytest.mark.asyncio
async def test_entitlements_report_the_counts_and_leave_other_keys_alone(client, db_session):  # AC13
    ctx = await mk_school(db_session, label="E20U-E", students=1)
    counselor = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    await login(client, ctx["coordinator"].email)
    before = {s["key"]: s["used"] for s in (await client.get("/api/v1/school/entitlements")).json()["services"]}
    assert (before["loan_assistance"], before["scholarship_assistance"]) == (0, 0)
    await login(client, counselor.email)
    await _open(client, ctx["students"][0], "scholarship")
    await login(client, ctx["coordinator"].email)
    after = {s["key"]: s["used"] for s in (await client.get("/api/v1/school/entitlements")).json()["services"]}
    assert after["scholarship_assistance"] == 1
    assert {k: v for k, v in after.items() if k != "scholarship_assistance"} == {k: v for k, v in before.items() if k != "scholarship_assistance"}


def test_scorecard_outcomes_and_pipeline_still_say_not_tracked():  # AC14, D9
    scholarship_area = next(area for area in SCORECARD_AREAS if area[0] == "scholarship")
    assert scholarship_area[2] is None
    assert "scholarships" in UNTRACKED_OUTCOMES
    assert "scholarship" in {key for key, _label, _note in NOT_TRACKED}
