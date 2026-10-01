"""ENH-020 -- migration 0053 (spec §3.1, AC15): single head, create-table only, matches the model, constraints enforced by the database."""

import importlib.util
import re
from datetime import date
from pathlib import Path
from typing import get_args

import pytest
from enh005_helpers import mk_school, mk_staff
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models import SchoolFundingRecord
from app.schemas import FundingStatus, FundingSupportType

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_enh_020_migration_0053", VERSIONS / "0053_school_funding_records.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)
TABLE = "school_funding_records"


def _parents() -> dict[str, str | None]:
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        parent = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
        if rev:
            parents[rev] = parent
    return parents


def test_migration_follows_0052_and_is_the_single_head():
    assert _migration.revision == "0053_school_funding_records"
    assert _migration.down_revision == "0052_agent_staff_permissions"
    parents = _parents()
    heads = set(parents) - set(parents.values())
    assert heads == {"0053_school_funding_records"}


@pytest.mark.asyncio
async def test_table_matches_the_model(db_session):
    def _describe(sync_conn):
        insp = inspect(sync_conn)
        return (
            {c["name"]: c["nullable"] for c in insp.get_columns(TABLE)},
            {c["name"] for c in insp.get_check_constraints(TABLE)},
            {i["name"]: (tuple(i["column_names"]), i["unique"]) for i in insp.get_indexes(TABLE)},
        )

    conn = await db_session.connection()
    columns, checks, indexes = await conn.run_sync(_describe)
    assert columns == {
        "id": False, "school_student_id": False, "school_id": False, "support_type": False, "status": False, "status_changed_on": False,
        "provider_name": True, "amount_text": True, "notes": False, "closure_reason": True, "career_counselor_user_id": False,
        "updated_by_user_id": True, "created_at": False, "updated_at": False,
    }
    assert checks == {"ck_funding_record_support_type", "ck_funding_record_status", "ck_funding_record_closure"}
    assert indexes == {
        "ix_school_funding_records_school_student_id": (("school_student_id",), False),
        "ix_school_funding_records_school_type": (("school_id", "support_type"), False),
        "uq_funding_record_open_student_type": (("school_student_id", "school_id", "support_type"), True),
    }


def _check_values(name: str) -> set[str]:
    constraint = next(c for c in SchoolFundingRecord.__table__.constraints if c.name == name)
    return set(re.findall(r"'([a-z_]+)'", str(constraint.sqltext)))


def test_the_check_constraints_list_exactly_the_schema_literals():
    assert _check_values("ck_funding_record_status") == set(get_args(FundingStatus))
    assert _check_values("ck_funding_record_support_type") == set(get_args(FundingSupportType))


async def _world(db) -> dict:
    """Plain ids, not ORM objects: a rollback below expires every object in the session."""
    ctx = await mk_school(db, label="E20M", students=1)
    counselor = await mk_staff(db, ctx["school"], ctx["admin"], role="career_counselor")
    return {"student_id": ctx["students"][0].id, "school_id": ctx["school"].id, "counselor_id": counselor.id}


def _row(ctx, **values) -> SchoolFundingRecord:
    defaults = {
        "school_student_id": ctx["student_id"], "school_id": ctx["school_id"], "support_type": "education_loan", "status": "required",
        "status_changed_on": date.today(), "career_counselor_user_id": ctx["counselor_id"],
    }
    return SchoolFundingRecord(**{**defaults, **values})


@pytest.mark.asyncio
async def test_closed_needs_a_reason_and_only_closed_has_one(db_session):
    ctx = await _world(db_session)
    for bad in ({"status": "closed"}, {"status": "required", "closure_reason": "why"}):
        db_session.add(_row(ctx, **bad))
        with pytest.raises(IntegrityError, match="ck_funding_record_closure"):
            await db_session.commit()
        await db_session.rollback()


@pytest.mark.asyncio
async def test_second_open_case_is_refused_but_a_finished_one_is_not(db_session):
    ctx = await _world(db_session)
    first = _row(ctx)
    db_session.add(first)
    await db_session.commit()
    db_session.add(_row(ctx, status="counselling"))
    with pytest.raises(IntegrityError, match="uq_funding_record_open_student_type"):
        await db_session.commit()
    await db_session.rollback()
    db_session.add(_row(ctx, support_type="scholarship"))  # another type is its own case
    await db_session.commit()
    first.status, first.closure_reason = "closed", "Bank refused"
    await db_session.commit()
    db_session.add(_row(ctx))  # the finished case no longer blocks a new one
    await db_session.commit()
