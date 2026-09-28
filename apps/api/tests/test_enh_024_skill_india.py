"""ENH-024 -- Skill India certification tracking.
docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md
"""

import json
import logging
from datetime import date
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import AuditLog, PortfolioEntry
from app.schemas import (
    CERT_CERTIFIED_ERROR,
    CERT_FIELDS_UNTAGGED_ERROR,
    CERT_STATUS_REQUIRED_ERROR,
    CERT_TYPE_SECTION_ERROR,
    PortfolioEntryCreate,
    PortfolioEntryUpdate,
    skill_india_error,
)
from tests.enh005_helpers import login, mk_school, mk_staff

ENTRIES = "/api/v1/school/students/{sid}/portfolio/entries"
ENTRY = ENTRIES + "/{eid}"
CERT = {"certification_type": "skill_india", "certification_status": "enrolled", "certificate_number": "SI-2026-0001", "issued_on": None}
CERT_KEYS = ("certification_type", "certification_status", "certificate_number", "issued_on")


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    """Same order-proofing as test_enh_003: an in-process Alembic run disables existing `app.*` loggers."""
    logging.getLogger("app.portfolio").disabled = False
    yield


async def _create(client, sid, **fields):
    body = {"section": "certification", "title": "Retail Sales Associate", "organization": "Retailers Association's Skill Council of India", **CERT, **fields}
    return await client.post(ENTRIES.format(sid=sid), json=body)


def _cert_fields(body: dict) -> tuple:
    return tuple(body[k] for k in CERT_KEYS)


def _row(ctx, **overrides) -> PortfolioEntry:
    fields = {"section": "certification", "title": "Retail Sales Associate", "created_by_user_id": ctx["coordinator"].id, "updated_by_user_id": ctx["coordinator"].id, **overrides}
    return PortfolioEntry(school_student_id=ctx["students"][0].id, **fields)


# --- Schema (migration 0042) --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_columns_are_nullable_and_sized(db_session):  # AC-10
    rows = (
        await db_session.execute(
            text(
                "SELECT column_name, data_type, character_maximum_length, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'portfolio_entries' AND column_name IN ('certification_type', 'certification_status', 'certificate_number', 'issued_on') "
                "ORDER BY column_name"
            )
        )
    ).all()
    assert [tuple(r) for r in rows] == [
        ("certificate_number", "character varying", 100, "YES"),
        ("certification_status", "character varying", 20, "YES"),
        ("certification_type", "character varying", 30, "YES"),
        ("issued_on", "date", None, "YES"),
    ]


@pytest.mark.asyncio
async def test_alembic_is_at_head_and_includes_0042(db_session):  # AC-10
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    script = ScriptDirectory.from_config(config)
    version = await db_session.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == script.get_current_head()
    assert "0042_skill_india_certification" in {rev.revision for rev in script.iterate_revisions(version, "base")}


@pytest.mark.asyncio
async def test_a_plain_entry_stays_untagged(db_session):  # AC-10, AC-12
    ctx = await mk_school(db_session, label="E24-Plain")
    entry = _row(ctx)
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    assert (entry.certification_type, entry.certification_status, entry.certificate_number, entry.issued_on) == (None, None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"section": "award", "certification_type": "skill_india", "certification_status": "enrolled"},
        {"certification_type": "nsdc", "certification_status": "enrolled"},
        {"certification_type": "skill_india"},
        {"certification_status": "enrolled"},
        {"certificate_number": "SI-1"},
        {"issued_on": date(2026, 5, 1)},
        {"certification_type": "skill_india", "certification_status": "passed"},
        {"certification_type": "skill_india", "certification_status": "certified", "issued_on": date(2026, 5, 1)},
        {"certification_type": "skill_india", "certification_status": "certified", "certificate_number": "SI-1"},
    ],
)
async def test_database_rejects_every_invalid_combination(db_session, overrides):  # AC-09
    ctx = await mk_school(db_session, label="E24-Check")
    db_session.add(_row(ctx, **overrides))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_database_accepts_a_certified_skill_india_row(db_session):  # AC-09
    ctx = await mk_school(db_session, label="E24-CheckOK")
    db_session.add(_row(ctx, certification_type="skill_india", certification_status="certified", certificate_number="SI-1", issued_on=date(2026, 5, 1)))
    await db_session.commit()


# --- Schemas ------------------------------------------------------------------------------------------------------

SKILL_INDIA = {"section": "certification", "title": "Retail Sales Associate", "certification_type": "skill_india"}


def test_create_accepts_a_skill_india_certification():
    entry = PortfolioEntryCreate(**SKILL_INDIA, certification_status="enrolled")
    assert (entry.certification_type, entry.certification_status, entry.certificate_number, entry.issued_on) == ("skill_india", "enrolled", None, None)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"section": "award", "certification_type": "skill_india", "certification_status": "enrolled"}, CERT_TYPE_SECTION_ERROR),
        ({"section": "certification", "certification_type": "skill_india"}, CERT_STATUS_REQUIRED_ERROR),
        ({"section": "certification", "certification_status": "enrolled"}, CERT_FIELDS_UNTAGGED_ERROR),
        ({"section": "certification", "certificate_number": "SI-1"}, CERT_FIELDS_UNTAGGED_ERROR),
        ({"section": "certification", "issued_on": "2026-05-01"}, CERT_FIELDS_UNTAGGED_ERROR),
        ({"section": "certification", "certification_type": "skill_india", "certification_status": "certified", "issued_on": "2026-05-01"}, CERT_CERTIFIED_ERROR),
        ({"section": "certification", "certification_type": "skill_india", "certification_status": "certified", "certificate_number": "SI-1"}, CERT_CERTIFIED_ERROR),
    ],
)
def test_create_rejects_with_a_plain_message(payload, message):  # AC-04
    with pytest.raises(ValidationError) as exc:
        PortfolioEntryCreate(title="Retail Sales Associate", **payload)
    assert message in exc.value.errors()[0]["msg"]


def test_create_accepts_explicit_nulls_on_an_untagged_entry():  # Review Focus 2
    entry = PortfolioEntryCreate(section="project", title="X", certification_type=None, certification_status=None, certificate_number=None, issued_on=None)
    assert entry.certification_type is None


def test_certificate_number_is_trimmed_and_blank_becomes_none():  # Review Focus 4
    assert PortfolioEntryCreate(**SKILL_INDIA, certification_status="enrolled", certificate_number="  SI-9 ").certificate_number == "SI-9"
    assert PortfolioEntryCreate(**SKILL_INDIA, certification_status="enrolled", certificate_number="   ").certificate_number is None


@pytest.mark.parametrize("bad", ["SI\n1", "SI\x001", "a" * 101])
def test_certificate_number_rejects_control_characters_and_overlength(bad):  # Review Focus 4
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(**SKILL_INDIA, certification_status="enrolled", certificate_number=bad)


@pytest.mark.parametrize("payload", [{"certification_type": "nsdc", "certification_status": "enrolled"}, {"certification_type": "skill_india", "certification_status": "passed"}])
def test_unknown_tag_or_status_is_rejected(payload):
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="certification", title="X", **payload)


def test_update_accepts_detail_fields_but_never_the_tag():  # AC-05
    update_ = PortfolioEntryUpdate(certification_status="certified", certificate_number="SI-1", issued_on="2026-05-01")
    assert update_.model_fields_set == {"certification_status", "certificate_number", "issued_on"}
    with pytest.raises(ValidationError):
        PortfolioEntryUpdate(certification_type="skill_india")


def test_skill_india_error_covers_every_rule():
    assert skill_india_error(None, None, None, None) is None
    assert skill_india_error(None, "enrolled", None, None) == CERT_FIELDS_UNTAGGED_ERROR
    assert skill_india_error("skill_india", None, None, None) == CERT_STATUS_REQUIRED_ERROR
    assert skill_india_error("skill_india", "certified", "SI-1", None) == CERT_CERTIFIED_ERROR
    assert skill_india_error("skill_india", "certified", "SI-1", date(2026, 5, 1)) is None
    assert skill_india_error("skill_india", "in_progress", None, None) is None


# --- Create + read (Portfolio and 360°), authorization, audit -----------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_creates_a_skill_india_certification(client, db_session):  # AC-01
    ctx = await mk_school(db_session, label="E24-Create")
    await login(client, ctx["coordinator"].email)
    r = await _create(client, ctx["students"][0].id)
    assert r.status_code == 201, r.text
    assert _cert_fields(r.json()) == ("skill_india", "enrolled", "SI-2026-0001", None)
    assert r.json()["organization"] == "Retailers Association's Skill Council of India"


@pytest.mark.asyncio
@pytest.mark.parametrize("writer", ["teacher", "academic_team"])
async def test_the_other_writers_can_create_too(client, db_session, writer):  # AC-01, D10
    ctx = await mk_school(db_session, label="E24-Writers")
    user = ctx["teacher"] if writer == "teacher" else await mk_staff(db_session, ctx["school"], ctx["admin"], role="academic_team")
    await login(client, user.email)
    assert (await _create(client, ctx["students"][0].id)).status_code == 201


@pytest.mark.asyncio
async def test_it_shows_on_portfolio_and_360_for_every_reader(client, db_session):  # AC-02
    ctx = await mk_school(db_session, label="E24-Read")
    sid = ctx["students"][0].id
    await login(client, ctx["coordinator"].email)
    created = (await _create(client, sid, certification_status="certified", issued_on="2026-05-01")).json()
    staff = [await mk_staff(db_session, ctx["school"], ctx["admin"], role=r) for r in ("academic_team", "career_counselor", "psychometric_team")]
    for reader in [ctx["coordinator"], ctx["teacher"], ctx["principal"], ctx["parent"], *staff]:
        await login(client, reader.email)
        portfolio = (await client.get(f"/api/v1/school/students/{sid}/portfolio")).json()
        view = (await client.get(f"/api/v1/school/students/{sid}/360-view")).json()
        [p] = portfolio["entries"]["certification"]
        [v] = view["tabs"]["certificates"]["data"]["entries"]
        assert p["id"] == v["id"] == created["id"], reader.role
        assert _cert_fields(p) == _cert_fields(v) == ("skill_india", "certified", "SI-2026-0001", "2026-05-01"), reader.role


@pytest.mark.asyncio
async def test_plain_certifications_and_completion_are_unchanged(client, db_session):  # AC-12
    ctx = await mk_school(db_session, label="E24-Plain", students=2)
    plain_kid, tagged_kid = ctx["students"]
    await login(client, ctx["coordinator"].email)
    plain = await client.post(ENTRIES.format(sid=plain_kid.id), json={"section": "certification", "title": "First aid"})
    assert plain.status_code == 201
    assert _cert_fields(plain.json()) == (None, None, None, None)
    assert (await _create(client, tagged_kid.id)).status_code == 201
    pct = [(await client.get(f"/api/v1/school/students/{k.id}/portfolio")).json()["completion_percentage"] for k in (plain_kid, tagged_kid)]
    assert pct[0] == pct[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["principal", "parent", "career_counselor", "psychometric_team"])
async def test_readers_who_are_not_writers_get_403(client, db_session, role):  # AC-06
    ctx = await mk_school(db_session, label="E24-NoWrite")
    user = ctx[role] if role in ctx else await mk_staff(db_session, ctx["school"], ctx["admin"], role=role)
    await login(client, user.email)
    assert (await _create(client, ctx["students"][0].id)).status_code == 403


@pytest.mark.asyncio
async def test_an_unassigned_teacher_gets_403(client, db_session):  # AC-06
    ctx = await mk_school(db_session, label="E24-Unassigned", students=2)
    await login(client, ctx["teacher"].email)
    assert (await _create(client, ctx["students"][1].id)).status_code == 403


@pytest.mark.asyncio
async def test_another_schools_coordinator_cannot_create(client, db_session):  # AC-06
    ctx = await mk_school(db_session, label="E24-Mine")
    other = await mk_school(db_session, label="E24-Other", admin=ctx["admin"])
    await login(client, other["coordinator"].email)
    r = await _create(client, ctx["students"][0].id)
    assert r.status_code in (403, 404)
    assert await db_session.scalar(select(PortfolioEntry).where(PortfolioEntry.school_student_id == ctx["students"][0].id)) is None


@pytest.mark.asyncio
async def test_below_gold_create_is_refused(client, db_session):  # AC-07
    ctx = await mk_school(db_session, label="E24-Silver", tier="silver")
    await login(client, ctx["coordinator"].email)
    r = await _create(client, ctx["students"][0].id)
    assert r.status_code == 403
    assert "Digital portfolio creation" in r.json()["detail"]


@pytest.mark.asyncio
async def test_create_audit_and_log_carry_the_tag_but_never_the_number(client, db_session, caplog):  # AC-11, D16
    ctx = await mk_school(db_session, label="E24-Audit")
    await login(client, ctx["coordinator"].email)
    with caplog.at_level(logging.INFO, logger="app.portfolio"):
        created = (await _create(client, ctx["students"][0].id)).json()
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.portfolio_entry_create", AuditLog.entity_id == created["id"]))
    assert row.metadata_json["certification_type"] == "skill_india"
    assert row.metadata_json["certification_status"] == "enrolled"
    assert "SI-2026-0001" not in json.dumps(row.metadata_json)
    records = [r for r in caplog.records if r.name == "app.portfolio"]
    assert any(getattr(r, "extra_fields", {}).get("certification_type") == "skill_india" for r in records)
    assert "SI-2026-0001" not in " ".join(r.getMessage() + json.dumps(getattr(r, "extra_fields", {}), default=str) for r in records)


@pytest.mark.asyncio
async def test_plain_entry_audit_metadata_is_exactly_as_before(client, db_session):  # AC-12
    ctx = await mk_school(db_session, label="E24-AuditPlain")
    await login(client, ctx["coordinator"].email)
    created = (await client.post(ENTRIES.format(sid=ctx["students"][0].id), json={"section": "project", "title": "Robot"})).json()
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "school.portfolio_entry_create", AuditLog.entity_id == created["id"]))
    assert set(row.metadata_json) == {"section", "school_student_id"}
