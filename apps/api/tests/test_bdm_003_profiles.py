"""bdm-003 -- type-specific profiles through the service and the API (spec §5, §7 AC1-AC8, §12)."""

import asyncio
import logging
import uuid

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, BdmOrganization
from app.services import bdm_organizations as svc
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import ORGS, create_org, unique_name
from tests.bdm003_helpers import bdm_of, profile_org


def _org(org_type: str, **values) -> BdmOrganization:
    return BdmOrganization(id=uuid.uuid4(), org_type=org_type, **values)


def _locs(exc: RequestValidationError) -> dict[str, str]:
    return {e["loc"][-1]: e["msg"] for e in exc.errors()}


def test_check_profile_allows_the_group_and_refuses_other_keys_by_presence():
    svc.check_profile("school", {"board": "CBSE", "grade_from": 6}, None)
    svc.check_profile("university", {"affiliation": "VTU"}, None)
    svc.check_profile("corporate", {}, None)
    with pytest.raises(RequestValidationError) as exc:
        svc.check_profile("college", {"board": None, "country": "India", "affiliation": "VTU"}, None)
    assert _locs(exc.value) == {"board": "Board is not a field for College organizations", "country": "Country is not a field for College organizations"}
    assert all(e["loc"][:2] == ("body", "profile") for e in exc.value.errors())
    with pytest.raises(RequestValidationError) as exc:
        svc.check_profile("other", {"courses": "MBA"}, None)
    assert _locs(exc.value) == {"courses": "Courses is not a field for Other organizations"}


def test_check_profile_grade_order_uses_stored_values_overlaid_by_sent():
    stored = _org("school", grade_from=6, grade_to=12)
    svc.check_profile("school", {"grade_to": 8}, stored)
    svc.check_profile("school", {"grade_from": None, "grade_to": 3}, stored)  # the stored lowest grade is cleared in the same request
    for sent in ({"grade_to": 5}, {"grade_from": 12, "grade_to": 6}, {"grade_from": 12, "grade_to": 11}):
        with pytest.raises(RequestValidationError) as exc:
            svc.check_profile("school", sent, stored)
        assert _locs(exc.value) == {"grade_to": "Lowest grade can't be above the highest grade"}


def test_check_type_change_refuses_across_groups_while_the_old_group_has_data():
    user = type("U", (), {"id": uuid.uuid4()})()
    svc.check_type_change(user, _org("college", affiliation="VTU"), "university")  # same group
    svc.check_type_change(user, _org("school"), "college")  # nothing entered
    svc.check_type_change(user, _org("corporate"), "school")  # no old group
    with pytest.raises(HTTPException) as exc:
        svc.check_type_change(user, _org("school", board="CBSE", grade_to=10), "agent")
    assert exc.value.status_code == 409
    assert exc.value.detail == {"message": "Clear the School details before changing the type", "code": "profile_not_empty", "fields": ["board", "grade_to"]}


def test_profile_out_per_group():
    assert svc.profile_out(_org("agent", country="India", staff_count=4)) == {"kind": "agent", "country": "India", "territory": None, "source": None, "staff_count": 4}
    assert svc.profile_out(_org("university", courses="MBA"))["kind"] == "college"
    assert svc.profile_out(_org("training_institute")) is None
