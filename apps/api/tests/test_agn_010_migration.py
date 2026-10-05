"""AGN-010 -- migration 0062_agent_offer_details (spec §3): four nullable offer columns, two checks, and the offer document link that
is cleared when its document is deleted. Lite: chain, model, shared database; the 0057 round-trip pattern is not repeated here."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import delete, inspect
from sqlalchemy.exc import IntegrityError

from app.models import OverseasApplication, StudentDocument
from tests.agn008_helpers import agency_world, mk_application
from tests.agn009_helpers import mk_doc

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_010_migration_0062", VERSIONS / "0062_agent_offer_details.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

NEW = ("offer_type", "offer_date", "offer_conditions", "offer_document_id")


def test_migration_chains_after_0061_and_is_the_single_head():
    assert _migration.revision == "0062_agent_offer_details"
    assert _migration.down_revision == "0061_bdm_profiles"
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    assert len(set(parents) - set(parents.values())) == 1


def test_model_declares_the_offer_columns_nullable():
    columns = OverseasApplication.__table__.columns
    for name in NEW:
        assert name in columns and columns[name].nullable, name


@pytest.mark.asyncio
async def test_offer_columns_and_checks_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    cols = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_columns("overseas_applications")})
    checks = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_check_constraints("overseas_applications")})
    assert set(NEW) <= cols
    assert {_migration.TYPE_CHECK, _migration.DATED_CHECK} <= checks


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [{"offer_type": "maybe", "offer_date": date(2026, 9, 1)}, {"offer_type": "conditional"}, {"offer_date": date(2026, 9, 1)}])
async def test_checks_refuse_an_unknown_type_and_a_type_without_a_date(db_session, fields):
    w = await agency_world(db_session)
    with pytest.raises(IntegrityError):
        await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"], **fields)
    await db_session.rollback()


@pytest.mark.asyncio
async def test_deleting_the_offer_letter_clears_the_link(db_session):
    w = await agency_world(db_session)
    app = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"], status="offer")
    doc = await mk_doc(db_session, record=w["record"], application=app, document_type="Offer letter")
    app.offer_type, app.offer_date, app.offer_document_id = "unconditional", date(2026, 9, 1), doc.id
    await db_session.commit()
    await db_session.execute(delete(StudentDocument).where(StudentDocument.id == doc.id))
    await db_session.commit()
    assert (await db_session.get(OverseasApplication, app.id, populate_existing=True)).offer_document_id is None
