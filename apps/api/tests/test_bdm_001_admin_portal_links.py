"""bdm-001 browser QA-05 (owner, 2026-10-02): a BDM manager's set-password link opens the admin portal's own reset page.
Every other role keeps its existing URL (super_admin stays on /it)."""

from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.provisioning import _set_password_url


@pytest.mark.parametrize(
    ("role", "division", "segment"),
    [("bdm_manager", "global", "admin"), ("super_admin", "global", "it"), ("bdm", "it", "it"), ("bdm", "overseas", "overseas"), ("counselor", "overseas", "overseas")],
)
def test_set_password_url_by_role(role, division, segment):
    url = _set_password_url(SimpleNamespace(role=role, division=division), "tok")
    assert url == f"{settings.frontend_url}/{segment}/reset-password?token=tok"
