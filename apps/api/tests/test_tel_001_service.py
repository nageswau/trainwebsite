"""tel-001 -- services/telecaller.py rules and scope helpers (spec §5.3)."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models import TelecallerProfile
from app.services import telecaller as rules
from tests.tel001_helpers import emp, make_tl_manager, make_user


def _actor(role: str):
    return SimpleNamespace(id=uuid.uuid4(), role=role)


@pytest.mark.parametrize(("role", "teams"), [("super_admin", {"it", "overseas"}), ("it_admin", {"it"}), ("overseas_admin", {"overseas"}), ("counselor", set())])
def test_creatable_teams(role, teams):
    assert rules.creatable_teams(_actor(role)) == teams


def test_require_creator_may_names_the_team():
    with pytest.raises(HTTPException) as caught:
        rules.require_creator_may(_actor("it_admin"), "overseas", "/admin/users")
    assert caught.value.status_code == 403 and caught.value.detail == "Your role cannot manage Overseas telecallers"
    rules.require_creator_may(_actor("it_admin"), "it", "/admin/users")


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (None, "Telecaller profile is required"),
        ({"employee_id": "E1", "reporting_manager_user_id": str(uuid.uuid4())}, "Team is required"),
        ({"team": "global", "employee_id": "E1", "reporting_manager_user_id": str(uuid.uuid4())}, "Team: Input should be 'it' or 'overseas'"),
        ({"team": "it", "employee_id": "   ", "reporting_manager_user_id": str(uuid.uuid4())}, "Employee ID is required"),
        ({"team": "it", "employee_id": "E1", "reporting_manager_user_id": "nope"}, "Reporting manager: choose a manager from the list"),
        ({"team": "it", "employee_id": "E1", "reporting_manager_user_id": str(uuid.uuid4()), "designation": "x"}, "Unknown field: designation"),
    ],
)
def test_parse_profile_create_gives_readable_422(raw, message):
    with pytest.raises(HTTPException) as caught:
        rules.parse_profile_create(raw)
    assert caught.value.status_code == 422 and caught.value.detail == message


def test_parse_profile_create_trims_employee_id():
    parsed = rules.parse_profile_create({"team": "it", "employee_id": "  E-7 ", "reporting_manager_user_id": str(uuid.uuid4())})
    assert parsed.employee_id == "E-7"


@pytest.mark.parametrize(("raw", "phone"), [({"phone": " +91 98 "}, "+91 98"), ({"phone": ""}, None), ({"phone": None}, None)])
def test_parse_self_update_accepts_and_clears_phone(raw, phone):
    assert rules.parse_self_update(raw).phone == phone


@pytest.mark.parametrize(
    ("raw", "message"),
    [({}, "Phone is required"), ({"phone": "abc"}, "Phone may contain only digits, spaces and + - ( )"), ({"phone": "1", "employee_id": "E"}, "Unknown field: employee_id")],
)
def test_parse_self_update_refuses(raw, message):
    with pytest.raises(HTTPException) as caught:
        rules.parse_self_update(raw)
    assert caught.value.status_code == 422 and caught.value.detail == message


@pytest.mark.asyncio
async def test_locked_active_manager_accepts_only_an_active_telecaller_manager(db_session):
    good = await make_tl_manager(db_session)
    assert (await rules.locked_active_manager(db_session, good.id)).id == good.id
    for bad in (await make_tl_manager(db_session, active=False), await make_user(db_session, "bdm_manager", "global")):
        with pytest.raises(HTTPException) as caught:
            await rules.locked_active_manager(db_session, bad.id)
        assert caught.value.status_code == 422 and caught.value.detail == "Reporting manager must be an active telecaller manager"
    with pytest.raises(HTTPException):
        await rules.locked_active_manager(db_session, uuid.uuid4())


def test_scope_helpers():
    assert rules.team_filter(_actor("super_admin")) == []
    assert len(rules.team_filter(_actor("telecaller_manager"))) == 1
    rules.require_manager(_actor("telecaller_manager"))
    rules.require_manager(_actor("super_admin"))
    for role in ("telecaller", "bdm_manager", "it_admin"):
        with pytest.raises(HTTPException) as caught:
            rules.require_manager(_actor(role))
        assert caught.value.status_code == 403 and caught.value.detail == "Telecaller manager role required"


def test_admin_team_filter():
    assert len(rules.admin_team_filter(_actor("it_admin"), None)) == 1
    assert len(rules.admin_team_filter(_actor("it_admin"), "it")) == 1
    with pytest.raises(HTTPException) as caught:
        rules.admin_team_filter(_actor("it_admin"), "overseas")
    assert caught.value.status_code == 403


@pytest.mark.asyncio
async def test_telecaller_context_requires_role_and_profile(db_session):
    with pytest.raises(HTTPException) as caught:
        await rules.telecaller_context(db_session, await make_user(db_session, "counselor", "overseas"))
    assert caught.value.detail == "Telecaller role required"
    bare = await make_user(db_session, "telecaller", "it")
    with pytest.raises(HTTPException) as caught:
        await rules.telecaller_context(db_session, bare)
    assert caught.value.detail == "Telecaller profile not set up — contact your administrator"
    manager = await make_tl_manager(db_session)
    db_session.add(TelecallerProfile(user_id=bare.id, team="it", employee_id=emp(), reporting_manager_user_id=manager.id))
    await db_session.commit()
    assert (await rules.telecaller_context(db_session, bare)).team == "it"
