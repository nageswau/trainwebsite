"""tel-003 -- the admin lead list: {items,total,limit,offset}, the stage/product/campaign/telecaller/source/search filters and the new
row keys (spec §4; AC3, AC4, T25). The shared test database is never truncated, so every test narrows to rows it created (a unique
`q` or a unique campaign/telecaller) before counting."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models import Enquiry, TelCampaign, TelProduct
from tests.bdm001_helpers import login, make_user
from tests.bdm017_helpers import ADMIN_LEADS, as_user, conversion

KEYS = {"id", "lead_code", "name", "email", "phone", "division", "subject", "status", "source", "crm_sync_status", "priority",
        "whatsapp_number", "city", "state", "qualification", "passing_year", "institution", "created_at", "stage_changed_at",
        "product", "campaign", "telecaller", "counselor", "organization", "bdm", "converted_user"}


def tag() -> str:
    return f"t3{uuid.uuid4().hex[:10]}"


async def lead(db, name: str, **over) -> Enquiry:
    values = {"division": "it", "name": name, "email": f"{uuid.uuid4().hex[:8]}@example.local", "phone": "9876543210",
              "subject": "Python", "message": "Hello there", "source": "website"} | over
    row = Enquiry(**values)
    db.add(row)
    await db.commit()
    return row


async def product(db, name: str = "Cyber Security", group: str = "it") -> TelProduct:
    """A tel-002 seed product."""
    return await db.scalar(select(TelProduct).where(TelProduct.product_group == group, TelProduct.name == name))


async def campaign(db, product_id) -> TelCampaign:
    row = TelCampaign(name=f"Campaign {tag()}", source="instagram", product_id=product_id, start_date=date(2026, 9, 1))
    db.add(row)
    await db.commit()
    return row


async def page(client, **params) -> dict:
    response = await client.get(ADMIN_LEADS, params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_the_list_is_a_page_with_the_new_row_keys(client, db_session):
    t = tag()
    cyber = await product(db_session)
    camp = await campaign(db_session, cyber.id)
    caller = await make_user(db_session, "telecaller", "it", name=f"Caller {t}")
    counselor = await make_user(db_session, "counselor", "it", name=f"Counselor {t}")
    row = await lead(db_session, f"Asha {t}", city="Kochi", state="Kerala", qualification="B.Tech", passing_year=2024,
                     institution="CUSAT", whatsapp_number="+919876543210", product_id=cyber.id, campaign_id=camp.id,
                     telecaller_user_id=caller.id, owner_id=counselor.id, priority="hot", source="instagram")
    await login(client, await make_user(db_session, "it_admin", "it"))
    data = await page(client, q=t)
    assert (set(data), data["total"], data["limit"], data["offset"]) == ({"items", "total", "limit", "offset"}, 1, 50, 0)
    item = data["items"][0]
    assert set(item) == KEYS
    assert (item["lead_code"], item["priority"], item["city"], item["passing_year"]) == (row.lead_code, "hot", "Kochi", 2024)
    assert item["product"] == {"id": str(cyber.id), "name": "Cyber Security"}
    assert item["campaign"] == {"id": str(camp.id), "name": camp.name}
    assert item["telecaller"] == {"id": str(caller.id), "full_name": f"Caller {t}"}
    assert item["counselor"] == {"id": str(counselor.id), "full_name": f"Counselor {t}"}
    assert (item["organization"], item["bdm"], item["converted_user"]) == (None, None, None)  # AC4: bdm-017 keys unchanged


@pytest.mark.asyncio
async def test_paging_is_newest_first_with_an_exact_total(client, db_session):
    t = tag()
    rows = [await lead(db_session, f"Lead {i} {t}") for i in range(3)]
    await login(client, await make_user(db_session, "it_admin", "it"))
    first = await page(client, q=t, limit=2)
    assert ([i["name"] for i in first["items"]], first["total"]) == ([f"Lead 2 {t}", f"Lead 1 {t}"], 3)
    second = await page(client, q=t, limit=2, offset=2)
    assert [i["id"] for i in second["items"]] == [str(rows[0].id)]
    past = await page(client, q=t, limit=2, offset=10)  # review focus 5
    assert (past["items"], past["total"]) == ([], 3)


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"product_id": "x"}, {"source": "tiktok"}])
async def test_bad_paging_or_filter_values_are_422(client, db_session, params):
    await login(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(ADMIN_LEADS, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_each_filter_narrows_to_the_matching_leads(client, db_session):
    t = tag()
    cyber, sap = await product(db_session), await product(db_session, "SAP")
    camp = await campaign(db_session, cyber.id)
    caller = await make_user(db_session, "telecaller", "it")
    a = await lead(db_session, f"A {t}", product_id=cyber.id, campaign_id=camp.id, telecaller_user_id=caller.id, status="contacted",
                   source="instagram")
    b = await lead(db_session, f"B {t}", product_id=sap.id, source="walk_in")
    await login(client, await make_user(db_session, "it_admin", "it"))
    for params, expected in (
        ({"product_id": str(cyber.id)}, [a]), ({"product_id": str(sap.id)}, [b]), ({"campaign_id": str(camp.id)}, [a]),
        ({"telecaller_user_id": str(caller.id)}, [a]), ({"status": "contacted"}, [a]), ({"source": "walk_in"}, [b]),
        ({"status": "new", "source": "walk_in"}, [b]), ({"status": "contacted", "source": "walk_in"}, []),
    ):
        data = await page(client, q=t, **params)
        assert [i["id"] for i in data["items"]] == [str(x.id) for x in expected], params
        assert data["total"] == len(expected)


@pytest.mark.asyncio
async def test_search_matches_lead_id_phone_email_and_subject_literally(client, db_session):
    t = tag()
    row = await lead(db_session, f"Search {t}", phone=f"+9198{uuid.uuid4().int % 10**8:08d}", subject=f"Interest {t}%")
    other = await lead(db_session, f"Other {t}", subject=f"Interest {t}x")
    await login(client, await make_user(db_session, "it_admin", "it"))
    for q in (row.lead_code, row.lead_code.lower(), row.phone[-8:], row.email.upper()):
        assert [i["id"] for i in (await page(client, q=q))["items"]] == [str(row.id)], q
    assert [i["id"] for i in (await page(client, q=f"{t}%"))["items"]] == [str(row.id)]  # review focus 3: % is literal
    assert {i["id"] for i in (await page(client, q=f"Interest {t}"))["items"]} == {str(row.id), str(other.id)}


@pytest.mark.asyncio
async def test_filters_never_widen_the_division_scope(client, db_session):
    """Review focus 2: an it_admin filtering by an overseas telecaller (or product) sees nothing from overseas."""
    t = tag()
    caller = await make_user(db_session, "telecaller", "overseas")
    uk = await product(db_session, "UK", "overseas")
    await lead(db_session, f"Overseas {t}", division="overseas", telecaller_user_id=caller.id, product_id=uk.id)
    await login(client, await make_user(db_session, "it_admin", "it"))
    for params in ({"telecaller_user_id": str(caller.id)}, {"product_id": str(uk.id)}, {"q": t}, {"division": "overseas", "q": t}):
        assert (await page(client, **params))["total"] == 0, params


@pytest.mark.asyncio
async def test_super_admin_sees_every_division_and_can_narrow_by_division(client, db_session):
    t = tag()
    await lead(db_session, f"It {t}")
    await lead(db_session, f"Os {t}", division="overseas")
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await page(client, q=t))["total"] == 2
    assert [i["division"] for i in (await page(client, q=t, division="overseas"))["items"]] == ["overseas"]


@pytest.mark.asyncio
async def test_non_admins_are_still_refused(client, db_session):
    for role, division in (("telecaller", "it"), ("counselor", "overseas"), ("it_student", "it")):
        await as_user(client, await make_user(db_session, role, division))
        assert (await client.get(ADMIN_LEADS)).status_code == 403


@pytest.mark.asyncio
async def test_the_conversion_answer_carries_the_new_keys(client, db_session):
    row = await lead(db_session, f"Convert {tag()}")
    student = await make_user(db_session, "it_student", "it")
    await login(client, await make_user(db_session, "it_admin", "it"))
    response = await client.post(conversion(row.id), json={"student_email": student.email})
    assert response.status_code == 200, response.text
    assert set(response.json()) == KEYS and response.json()["lead_code"] == row.lead_code
