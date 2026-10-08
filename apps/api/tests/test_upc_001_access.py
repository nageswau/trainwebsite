"""upc-001 PU9 / U2 -- who may see university commission data, and the new roles' permission bundles."""

import pytest

from app.core.rbac import PERMISSIONS, has_permission
from app.models import User
from app.services.partnership_access import can_see_commission


@pytest.mark.parametrize("role", ["super_admin", "partnership_manager", "partnership_head"])
def test_commission_roles_see_commission(role):
    assert can_see_commission(User(role=role))


@pytest.mark.parametrize("role", ["counselor", "overseas_admin", "agent", "university_rep", "bdm", "bdm_manager", "overseas_student", "telecaller", "it_admin"])
def test_every_other_role_does_not(role):
    assert not can_see_commission(User(role=role))


def test_roles_have_coarse_bundles():
    assert PERMISSIONS["partnership_manager"] == {"partnership:self"}
    assert PERMISSIONS["partnership_head"] == {"partnership:team"}
    assert not has_permission("partnership_manager", "partnership:team")
