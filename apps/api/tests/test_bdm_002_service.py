"""bdm-002 -- pure service rules (spec §5.2)."""

import logging
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import bdm_organizations as svc


def test_normalize_key_folds_case_whitespace_and_compatibility_forms():
    assert svc.normalize_key("  St.  MARY'S\tCollege ") == "st. mary's college"
    assert svc.normalize_key("ＳＴ ＭＡＲＹ") == svc.normalize_key("st mary")  # full-width (NFKC, §12.3)
    assert svc.normalize_key("Straße") == svc.normalize_key("STRASSE")  # casefold, not lower


def test_format_code_pads_to_six_and_grows_past_it():
    assert svc.format_code(123) == "ORG-000123"
    assert svc.format_code(1_234_567) == "ORG-1234567"


def _org(assignee, archived=False):
    return SimpleNamespace(id=uuid.uuid4(), assigned_bdm_user_id=assignee, archived_at=datetime.now(UTC) if archived else None)


def _user(role):
    return SimpleNamespace(id=uuid.uuid4(), role=role)


def test_permissions_table():
    bdm, other, manager, admin = _user("bdm"), _user("bdm"), _user("bdm_manager"), _user("super_admin")
    active, archived = _org(bdm.id), _org(bdm.id, archived=True)
    flags = lambda u, o: {k for k, v in svc.permissions(u, o).items() if v}  # noqa: E731
    assert flags(bdm, active) == {"can_edit", "can_archive"}
    assert flags(other, active) == set()
    assert flags(manager, active) == {"can_reassign"}
    assert flags(admin, active) == {"can_edit", "can_archive", "can_reassign"}
    assert flags(bdm, archived) == set()
    assert flags(manager, archived) == {"can_restore"}
    assert flags(admin, archived) == {"can_restore"}


@pytest.mark.parametrize(
    ("role", "own", "archived", "action", "status", "detail"),
    [
        ("bdm", False, False, "can_edit", 403, "Only the assigned BDM can edit this organization"),
        ("bdm_manager", False, False, "can_edit", 403, "Only the assigned BDM can edit this organization"),
        ("bdm", True, True, "can_edit", 409, "Restore this organization first"),
        ("bdm", True, True, "can_archive", 409, "Already archived"),
        ("bdm", True, False, "can_restore", 403, "Only the BDM's manager can restore this organization"),
        ("bdm_manager", False, False, "can_restore", 409, "Already active"),
        ("bdm", True, False, "can_reassign", 403, "Only the BDM's manager can reassign this organization"),
        ("bdm_manager", False, True, "can_reassign", 409, "Restore this organization first"),
    ],
)
def test_require_checks_the_role_before_the_state(role, own, archived, action, status, detail, caplog):
    # alembic's fileConfig (the migration tests) disables existing loggers; re-enable, as test_bdm_001_service does.
    logging.getLogger("app.bdm").disabled = False
    user = _user(role)
    org = _org(user.id if own else uuid.uuid4(), archived)
    with caplog.at_level(logging.WARNING, logger="app.bdm"), pytest.raises(HTTPException) as exc:
        svc.require(user, org, action, "test")
    assert (exc.value.status_code, exc.value.detail) == (status, detail)
    refused = [r for r in caplog.records if r.getMessage() == "bdm_org_write_refused"]
    if status == 403:
        assert set(refused[0].extra_fields) == {"actor_id", "org_id", "route", "action"}  # ids only, no PII (spec §12.3)
    else:
        assert not refused


def test_duplicate_conflict_shape():
    exc = svc.duplicate_conflict([{"id": "x"}], 3)
    assert exc.status_code == 409
    assert exc.detail["code"] == "possible_duplicate" and exc.detail["total"] == 3 and exc.detail["matches"] == [{"id": "x"}]
