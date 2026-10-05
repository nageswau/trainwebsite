"""tel-001 TL8: PATCH /auth/me is locked to the phone for a telecaller; every other role is unchanged."""

import pytest
from sqlalchemy import select

from app.models import User
from tests.tel001_helpers import login, make_user

URL = "/api/v1/auth/me"
LOCK = "Telecallers can change only their phone number — contact your administrator"
PHONE_422 = "Phone may contain only digits, spaces and + - ( )"


async def _telecaller(client, db):
    user = await make_user(db, "telecaller", "it", name="Ravi Telecaller")
    await db.refresh(user)
    user_id = user.id
    await login(client, user)
    return user_id


async def _stored(db, user_id, column):
    db.expire_all()
    return await db.scalar(select(column).where(User.id == user_id))


@pytest.mark.asyncio
async def test_telecaller_name_change_is_refused(client, db_session):
    user_id = await _telecaller(client, db_session)
    response = await client.patch(URL, json={"full_name": "Someone Else"})
    assert response.status_code == 403
    assert response.json()["detail"] == LOCK
    assert await _stored(db_session, user_id, User.full_name) == "Ravi Telecaller"


@pytest.mark.asyncio
async def test_telecaller_same_name_with_new_phone_saves_phone(client, db_session):
    user_id = await _telecaller(client, db_session)
    response = await client.patch(URL, json={"full_name": "Ravi Telecaller", "phone": " +91 98765 43210 "})
    assert response.status_code == 200, response.text
    assert await _stored(db_session, user_id, User.phone) == "+91 98765 43210"
    cleared = await client.patch(URL, json={"full_name": "Ravi Telecaller", "phone": None})
    assert cleared.status_code == 200
    assert await _stored(db_session, user_id, User.phone) is None


@pytest.mark.asyncio
async def test_telecaller_invalid_phone_is_422(client, db_session):
    await _telecaller(client, db_session)
    response = await client.patch(URL, json={"full_name": "Ravi Telecaller", "phone": "abc"})
    assert response.status_code == 422
    assert response.json()["detail"] == PHONE_422


@pytest.mark.asyncio
async def test_telecaller_profile_change_is_refused(client, db_session):
    user_id = await _telecaller(client, db_session)
    response = await client.patch(URL, json={"profile": {"bio": "hello"}})
    assert response.status_code == 403
    assert response.json()["detail"] == LOCK
    assert not await _stored(db_session, user_id, User.profile)


@pytest.mark.asyncio
async def test_other_roles_can_still_change_their_name(client, db_session):
    for role, division in (("bdm", "global"), ("it_student", "it")):
        user = await make_user(db_session, role, division, name="Old Name")
        await db_session.refresh(user)
        user_id = user.id
        await login(client, user)
        response = await client.patch(URL, json={"full_name": "New Name"})
        assert response.status_code == 200, (role, response.text)
        assert await _stored(db_session, user_id, User.full_name) == "New Name"
