"""rec-022 -- migration 0138_offer_management (spec §2, OF10). The status mapping, the CHECKs, the round trip and the downgrade refusal run in
a throwaway database built from scratch (the rec-017 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_rec_017_migration import _external, _job
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_022_migration_0138", VERSIONS / "0138_offer_management.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0137_resume_search", "0138_offer_management"


def test_migration_chains_and_there_is_a_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import OFFER_CHECKS, OFFER_EVENT_CHECKS, OFFER_EVENTS, OFFER_STATUSES, JobOffer, JobOfferEvent

    assert _migration.CHECKS == OFFER_CHECKS and _migration.EVENT_CHECKS == OFFER_EVENT_CHECKS
    assert _migration.STATUSES == OFFER_STATUSES == ("offer_pending", "offer_received", "accepted", "declined")
    assert _migration.EVENTS == OFFER_EVENTS
    table = JobOffer.__table__
    assert not table.c.status.nullable and table.c.position.nullable and table.c.created_by_user_id.nullable
    names = {c.name for t in (table, JobOfferEvent.__table__) for c in t.constraints} | {i.name for i in JobOfferEvent.__table__.indexes}
    assert set(OFFER_CHECKS) | set(OFFER_EVENT_CHECKS) | {"ix_job_offer_events_offer"} <= names
    assert {c.name for c in JobOfferEvent.__table__.columns} == {
        "id",
        "offer_id",
        "event",
        "from_status",
        "to_status",
        "fields",
        "note",
        "letter_key",
        "actor_user_id",
        "position",
        "created_at",
    }


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec022_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)  # the real 0137 shape of `job_offers`
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _application(url) -> uuid.UUID:
    app_id, job_id = uuid.uuid4(), _job(url)
    _sql(
        url,
        "INSERT INTO job_applications (id, job_id, candidate_id, status, stage_changed_at, created_at, updated_at) VALUES (:id, :j, :c, 'selected', now(), now(), now())",
        {"id": app_id, "j": job_id, "c": _external(url, email=f"{app_id.hex[:10]}@example.com")},
    )
    return app_id


def _offer(url, status: str) -> uuid.UUID:
    offer_id = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO job_offers (id, application_id, offered_on, currency, status, created_at, updated_at) VALUES (:id, :a, current_date, 'INR', :s, now(), now())",
        {"id": offer_id, "a": _application(url), "s": status},
    )
    return offer_id


def test_upgrade_maps_the_legacy_statuses(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    legacy = ("offered", "accepted", "joined", "declined", "rejected", "withdrawn", "pending", "on hold")
    rows = {word: _offer(url, word) for word in legacy}
    command.upgrade(cfg, HEAD)
    stored = dict(_sql(url, "SELECT id, status FROM job_offers"))
    assert {word: stored[rows[word]] for word in legacy} == {
        "offered": "offer_received",
        "accepted": "accepted",
        "joined": "accepted",
        "declined": "declined",
        "rejected": "declined",
        "withdrawn": "declined",
        "pending": "offer_pending",
        "on hold": "offer_received",
    }
    assert _sql(url, "SELECT count(*) FROM job_offer_events") == [(0,)]


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="ck_job_offers_status"):
        _offer(url, "offered")
    offer = _offer(url, "offer_pending")
    with pytest.raises(Exception, match="ck_job_offer_events_event"):
        _sql(url, "INSERT INTO job_offer_events (id, offer_id, event, created_at) VALUES (:id, :o, 'lunch', now())", {"id": uuid.uuid4(), "o": offer})
    assert _sql(url, "SELECT column_default FROM information_schema.columns WHERE table_name = 'job_offers' AND column_name = 'status'") == [("'offer_received'::character varying",)]
    command.downgrade(cfg, BASE)
    assert "position" not in {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'job_offers'")}
    assert _sql(url, "SELECT to_regclass('job_offer_events')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_history_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    offer = _offer(url, "offer_pending")
    _sql(url, "INSERT INTO job_offer_events (id, offer_id, event, to_status, created_at) VALUES (:id, :o, 'created', 'offer_pending', now())", {"id": uuid.uuid4(), "o": offer})
    with pytest.raises(Exception, match="offer history exists"):
        command.downgrade(cfg, BASE)
