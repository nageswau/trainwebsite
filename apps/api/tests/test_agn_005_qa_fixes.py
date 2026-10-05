"""AGN-005 browser QA fixes (owner, in-session 2026-10-01).

QA5-01: an agency student's phone follows the school mobile rule (`schemas._MOBILE`): digits, spaces, + - ( ), 7-20 characters, at
least 7 digits. Only a phone that is sent is checked, so a value saved before the rule (e.g. "abc") survives edits of other fields.
"""

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import select

from app.models import AgentStudent
from app.schemas import AgentStudentRecordCreate, AgentStudentRecordUpdate
from tests.agn001_helpers import client_for, mk_active_org, uniq
from tests.agn004_helpers import RECORDS, mk_record, mk_staff

PHONE_MESSAGE = "Enter a phone number of 7–20 digits, spaces, +, -, ( or ) with at least 7 digits"


@pytest_asyncio.fixture
async def agency(db_session):
    ctx = await mk_active_org(db_session, name="Phone Rule Agency")
    staff = await mk_staff(db_session, ctx["org"], full_name="Phone Staff")
    return ctx | {"staff": staff}


@pytest.mark.parametrize("phone", ["abc", "98765 4321x", "123456", "12-34-5", "+", "9" * 21, "Tel: 9876543210"])
def test_an_invalid_phone_is_refused_by_both_schemas(phone):
    for schema, extra in ((AgentStudentRecordCreate, {"full_name": "Asha"}), (AgentStudentRecordUpdate, {})):
        with pytest.raises(ValidationError) as caught:
            schema(**extra, phone=phone)
        error = caught.value.errors()[0]
        assert error["loc"] == ("phone",) and error["msg"] == PHONE_MESSAGE


@pytest.mark.parametrize("phone", ["9876543", "+91 98765 43210", "(022) 2345-6789", "  +44 20 7946 0958  "])
def test_a_valid_phone_is_kept_as_typed_but_trimmed(phone):
    assert AgentStudentRecordCreate(full_name="Asha", phone=phone).phone == phone.strip()


@pytest.mark.parametrize("phone", [None, "", "   "])
def test_no_phone_is_still_allowed(phone):
    assert AgentStudentRecordCreate(full_name="Asha", phone=phone).phone is None


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["master", "staff"])
async def test_create_with_an_invalid_phone_is_422_on_the_phone_field_and_saves_nothing(db_session, agency, who):
    email = agency["master"].email if who == "master" else agency["staff"]["user"].email
    name = f"Bad Phone {uniq()}"  # the test database keeps rows between runs
    async with client_for(email) as c:
        response = await c.post(RECORDS, json={"full_name": name, "phone": "abc"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "phone"] and response.json()["detail"][0]["msg"] == PHONE_MESSAGE
    assert await db_session.scalar(select(AgentStudent.id).where(AgentStudent.full_name == name)) is None


@pytest.mark.asyncio
async def test_edit_to_an_invalid_phone_is_422_and_changes_nothing(db_session, agency):
    row = await mk_record(db_session, agent=agency["master"], full_name="Edit Phone", phone="9876543210")
    async with client_for(agency["master"].email) as c:
        response = await c.patch(f"{RECORDS}/{row.id}", json={"phone": "abc"})
    assert response.status_code == 422 and response.json()["detail"][0]["loc"] == ["body", "phone"]
    row = await db_session.get(AgentStudent, row.id, populate_existing=True)
    assert row.phone == "9876543210"


@pytest.mark.asyncio
async def test_a_phone_saved_before_the_rule_survives_an_edit_of_another_field(db_session, agency):
    row = await mk_record(db_session, agent=agency["master"], full_name="Legacy Phone", phone="abc")
    async with client_for(agency["master"].email) as c:
        response = await c.patch(f"{RECORDS}/{row.id}", json={"full_name": "Legacy Phone Renamed"})
    assert response.status_code == 200 and response.json()["student"]["phone"] == "abc"
    row = await db_session.get(AgentStudent, row.id, populate_existing=True)
    assert (row.full_name, row.phone) == ("Legacy Phone Renamed", "abc")
