"""upc-019 -- Appendix B F10 / F11 on the §18 performance endpoints (spec CL13): Commission Expected / Received for the period, for the
commission roles only. Reads May 2019 (IST), a period no other test writes, so the shared DB's other rows never count."""

from datetime import UTC, date, datetime

import pytest

from app.models import UniversityCommissionReceipt
from tests.agn003_helpers import mk_university
from tests.upc001_helpers import as_role, make_head
from tests.upc003_helpers import login
from tests.upc019_helpers import agreement, enrolled, staff, term, tuition_course

MAY_2019 = {"from": "2019-05-01", "to": "2019-05-31", "limit": "100"}
IN_MAY = datetime(2019, 5, 10, 6, tzinfo=UTC)


async def _scene(db):
    """One university: two enrolments in May 2019 at 15% of GBP 18,000, one in June; GBP 1,000 received in May and USD 50 in April."""
    uni, by = await mk_university(db), await staff(db)
    c = await tuition_course(db, uni)
    await term(db, await agreement(db, uni, by, start=date(2019, 1, 1), expiry=date(2021, 1, 1)), by)
    for at in (IN_MAY, IN_MAY, datetime(2019, 6, 2, 6, tzinfo=UTC)):
        await enrolled(db, uni, c, at=at)
    for amount, currency, day in (("1000", "GBP", date(2019, 5, 20)), ("50", "USD", date(2019, 4, 30))):
        db.add(UniversityCommissionReceipt(university_id=uni.id, amount=amount, currency=currency, received_on=day, reference=f"R-{currency}", created_by_user_id=by.id))
    await db.commit()
    return uni


EXPECTED = {"expected": [{"currency": "GBP", "amount": "5400.00"}], "received": [{"currency": "GBP", "amount": "1000.00"}]}


@pytest.mark.asyncio
async def test_f10_f11_for_the_head_on_the_ranking_and_one_university(client, db_session):
    uni = await _scene(db_session)
    await login(client, await make_head(db_session))
    page = (await client.get("/api/v1/partnership/performance", params=MAY_2019)).json()
    row = next(r for r in page["items"] if r["university"]["id"] == str(uni.id))
    assert row["counts"]["enrolled"] == 2 and row["commission"] == EXPECTED
    gbp = next(x for x in page["commission"]["expected"] if x["currency"] == "GBP")  # the totals add every ranked row
    assert float(gbp["amount"]) >= 5400
    one = (await client.get(f"/api/v1/partnership/universities/{uni.id}/performance", params={"from": "2019-05-01", "to": "2019-05-31"})).json()
    assert one["commission"] == EXPECTED and one["counts"]["enrolled"] == 2


@pytest.mark.asyncio
async def test_overseas_admin_reads_the_counts_but_never_a_commission_key(client, db_session):
    uni = await _scene(db_session)
    await as_role(client, db_session, "overseas_admin", "overseas")
    page = await client.get("/api/v1/partnership/performance", params=MAY_2019)
    assert page.status_code == 200 and "commission" not in page.json()
    row = next(r for r in page.json()["items"] if r["university"]["id"] == str(uni.id))
    assert "commission" not in row and row["counts"]["leads"] is None  # untracked steps keep their explicit null
    one = await client.get(f"/api/v1/partnership/universities/{uni.id}/performance", params={"from": "2019-05-01", "to": "2019-05-31"})
    assert one.status_code == 200 and "commission" not in one.json() and "5400" not in one.text
