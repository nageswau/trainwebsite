"""bdm-003 -- migration 0068_bdm_org_profiles (spec §4). Round trip and the downgrade refusal run in a throwaway database (the
bdm-002 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
BASE = "0067_audit_entity_index"
HEAD = "0068_bdm_org_profiles"
NEW_COLUMNS = {"address", "country", "territory", "source", "staff_count", "board", "school_type", "grade_from", "grade_to", "affiliation", "college_type", "courses"}


def _migration():
    spec = importlib.util.spec_from_file_location("_bdm_003_migration_0068", VERSIONS / f"{HEAD}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _model_checks() -> dict[str, str]:
    from app.models import BdmOrganization

    return {c.name: str(c.sqltext) for c in BdmOrganization.__table__.constraints if isinstance(c, CheckConstraint)}


def test_model_has_the_profile_columns_and_checks():
    from app.models import BDM_PROFILE_CHECKS, BdmOrganization

    assert NEW_COLUMNS <= {c.name for c in BdmOrganization.__table__.columns}
    assert all(BdmOrganization.__table__.c[name].nullable for name in NEW_COLUMNS)
    assert set(BDM_PROFILE_CHECKS) == {
        "ck_bdm_organizations_source", "ck_bdm_organizations_staff_count", "ck_bdm_organizations_board", "ck_bdm_organizations_school_type",
        "ck_bdm_organizations_grades", "ck_bdm_organizations_college_type", "ck_bdm_organizations_agent_profile",
        "ck_bdm_organizations_school_profile", "ck_bdm_organizations_college_profile",
    }
    assert BDM_PROFILE_CHECKS.items() <= _model_checks().items()
