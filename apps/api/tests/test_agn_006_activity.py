"""AGN-006 -- a counseling save appears in the Master's Staff Activity with field names only (spec §5.6; DEC-SCOPE-048 C7; AC06)."""

import pytest

from tests.agn001_helpers import client_for, mk_active_org, uniq
from tests.agn002_helpers import STAFF, mk_staff
from tests.agn004_helpers import RECORDS, mk_record


@pytest.mark.asyncio
async def test_counseling_save_shows_field_names_and_no_values(db_session):
    ctx = await mk_active_org(db_session, name=f"Counseling Activity {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], full_name="Activity Counselor")
    row = await mk_record(db_session, agent=ctx["master"], full_name="Ravi Kumar", assigned_member=staff["member"])
    async with client_for(staff["user"].email) as s:
        saved = await s.put(f"{RECORDS}/{row.id}/counseling", json={"counseling_completed": True, "budget_amount": "4200000", "remarks": "Private remark 7731"})
    assert saved.status_code == 200, saved.text
    async with client_for(ctx["master"].email) as m:
        page = await m.get(f"{STAFF}/{staff['member'].id}/activity")
    assert page.status_code == 200
    [item] = page.json()["items"]
    assert (item["action"], item["subject"], item["fields"]) == ("agent_student.counseling", "Ravi Kumar", ["budget_amount", "budget_currency", "counseling_completed", "remarks"])
    assert "4200000" not in page.text and "7731" not in page.text
