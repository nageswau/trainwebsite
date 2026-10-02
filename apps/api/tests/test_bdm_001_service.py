"""bdm-001 -- services/bdm.py and the profile schemas (spec §5.2, §5.3). Pure units; no HTTP."""

import logging
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.rbac import PERMISSIONS
from app.services import bdm

MGR = str(uuid.uuid4())


def _actor(role):
    return SimpleNamespace(id=uuid.uuid4(), role=role)


def _valid(**patch):
    return {"bdm_type": "college", "employee_id": "E-1", "reporting_manager_user_id": MGR, **patch}


def test_roles_registered():
    assert PERMISSIONS["bdm"] == {"bdm:self"}
    assert PERMISSIONS["bdm_manager"] == {"bdm:team"}


def test_division_map_and_creator_matrix():
    assert bdm.BDM_DIVISION == {"college": "it", "agent": "overseas", "school": "overseas"}
    assert bdm.creatable_types(_actor("super_admin")) == {"agent", "school", "college"}
    assert bdm.creatable_types(_actor("it_admin")) == {"college"}
    assert bdm.creatable_types(_actor("overseas_admin")) == {"agent", "school"}
    assert bdm.creatable_types(_actor("counselor")) == frozenset()


@pytest.mark.parametrize(("role", "bdm_type"), [("it_admin", "agent"), ("overseas_admin", "college"), ("counselor", "school")])
def test_creator_refusal_is_403_and_logged_without_pii(role, bdm_type, caplog):
    logging.getLogger("app.bdm").disabled = False
    with caplog.at_level(logging.WARNING, logger="app.bdm"), pytest.raises(HTTPException) as exc:
        bdm.require_creator_may(_actor(role), bdm_type, "/api/v1/admin/users")
    assert exc.value.status_code == 403
    record = next(r for r in caplog.records if r.getMessage() == "bdm_creator_type_refused")
    assert set(record.extra_fields) == {"actor_id", "route", "bdm_type"}


def test_permitted_creator_passes():
    bdm.require_creator_may(_actor("it_admin"), "college", "/x")


def test_parse_create_trims_and_clears_blank_optionals():
    profile = bdm.parse_profile_create(_valid(employee_id="  E-1 ", designation=" "))
    assert profile.employee_id == "E-1"
    assert profile.designation is None
    assert str(profile.reporting_manager_user_id) == MGR


@pytest.mark.parametrize("raw", [None, "x", [], 5])
def test_profile_not_an_object_is_422(raw):
    for parse in (bdm.parse_profile_create, bdm.parse_profile_update):
        with pytest.raises(HTTPException) as exc:
            parse(raw)
        assert exc.value.status_code == 422


@pytest.mark.parametrize(
    ("patch", "detail"),
    [
        # QA-08: readable messages for admins -- no "bdm_profile.<field>:" path and no pydantic "Value error, " prefix.
        ({"bdm_type": "it"}, "Module: Input should be 'agent', 'school' or 'college'"),
        ({"employee_id": "   "}, "Employee ID is required"),
        ({"employee_id": "x" * 41}, "Employee ID must be at most 40 characters"),
        ({"employee_id": "E\x07"}, "Employee ID contains invalid characters"),
        ({"designation": "d" * 121}, "Designation: String should have at most 120 characters"),
        ({"reporting_manager_user_id": "not-a-uuid"}, "Reporting manager: choose a manager from the list"),
        ({"user_id": MGR}, "Unknown field: user_id"),
        ({"surprise": 1}, "Unknown field: surprise"),
    ],
)
def test_create_rejects_bad_fields_with_a_readable_422(patch, detail):
    with pytest.raises(HTTPException) as exc:
        bdm.parse_profile_create(_valid(**patch))
    assert exc.value.status_code == 422
    assert exc.value.detail == detail


def test_optional_texts_are_trimmed_before_the_length_check():
    """Deferred minor: a padded value that fits after trimming is accepted (it used to be measured with its padding)."""
    padded = "  " + "d" * 120 + "  "
    assert bdm.parse_profile_create(_valid(designation=padded)).designation == "d" * 120
    with pytest.raises(HTTPException) as exc:
        bdm.parse_profile_create(_valid(territory="t" * 121))
    assert exc.value.detail == "Territory: String should have at most 120 characters"


@pytest.mark.parametrize("field", ["designation", "department", "territory"])
def test_optional_texts_reject_control_characters_like_the_employee_id(field):
    """Deferred minor: the same rule as the Employee ID -- no control characters in any profile text."""
    with pytest.raises(HTTPException) as exc:
        bdm.parse_profile_create(_valid(**{field: "Sales\x07"}))
    assert exc.value.detail == f"{bdm.FIELD_LABELS[field]} contains invalid characters"
    with pytest.raises(HTTPException):
        bdm.parse_profile_update({field: "line\nbreak"})


@pytest.mark.asyncio
async def test_manager_lock_is_shared_not_exclusive(db_session):
    """Deferred minor: FOR SHARE still blocks a concurrent deactivation (an UPDATE of the manager row) but no longer makes two
    BDM creates under the same manager wait for each other, as FOR UPDATE did."""
    from sqlalchemy import event

    from tests.bdm001_helpers import make_manager

    manager = await make_manager(db_session)
    manager_id = manager.id
    seen: list[str] = []
    engine = db_session.bind.sync_engine
    listener = lambda conn, cursor, statement, *rest: seen.append(statement)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        assert (await bdm.locked_active_manager(db_session, manager_id)).id == manager_id
    finally:
        event.remove(engine, "before_cursor_execute", listener)
        await db_session.rollback()
    locking = [s for s in seen if "FROM users" in s and "FOR " in s]
    assert locking and all("FOR SHARE" in s for s in locking), locking


def test_missing_and_null_required_fields_read_plainly():
    raw = _valid()
    del raw["employee_id"]
    with pytest.raises(HTTPException) as exc:
        bdm.parse_profile_create(raw)
    assert exc.value.detail == "Employee ID is required"
    with pytest.raises(HTTPException) as exc:
        bdm.parse_profile_update({"reporting_manager_user_id": None})
    assert exc.value.detail == "Reporting manager is required"


def test_create_requires_type_employee_id_and_manager():
    for key in ("bdm_type", "employee_id", "reporting_manager_user_id"):
        raw = _valid()
        del raw[key]
        with pytest.raises(HTTPException) as exc:
            bdm.parse_profile_create(raw)
        assert exc.value.status_code == 422


def test_update_null_semantics():
    assert bdm.parse_profile_update({"territory": None}).model_dump(exclude_unset=True) == {"territory": None}
    assert bdm.parse_profile_update({"territory": ""}).territory is None
    for key in ("employee_id", "reporting_manager_user_id", "bdm_type"):
        with pytest.raises(HTTPException) as exc:
            bdm.parse_profile_update({key: None})
        assert exc.value.status_code == 422
    assert bdm.parse_profile_update({}).model_dump(exclude_unset=True) == {}


def test_scope_helpers():
    manager, super_admin = _actor("bdm_manager"), _actor("super_admin")
    assert bdm.team_filter(super_admin) == []
    assert len(bdm.team_filter(manager)) == 1
    bdm.require_manager(manager)
    bdm.require_manager(super_admin)
    for role in ("bdm", "counselor", "it_admin"):
        with pytest.raises(HTTPException) as exc:
            bdm.require_manager(_actor(role))
        assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        bdm.admin_type_filter(_actor("it_admin"), "agent")
    assert exc.value.status_code == 403
    assert len(bdm.admin_type_filter(_actor("it_admin"), None)) == 1
    assert len(bdm.admin_type_filter(_actor("overseas_admin"), "school")) == 1
