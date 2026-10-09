"""rec-023 -- migration 0140_joining_management (spec §2, JN1-JN3). The backfill, the CHECKs, the round trip and the downgrade refusal run in a
throwaway database built from scratch (the rec-017 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_rec_023_migration_0140", VERSIONS / "0140_joining_management.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0139_recruiter_contracts", "0140_joining_management"


def test_migration_chains_and_there_is_a_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import JOINING_CHECKS, JOINING_STATUSES, OFFER_EVENT_CHECKS, OFFER_EVENTS, JobOffer

    assert _migration.CHECKS == JOINING_CHECKS and _migration.EVENT_CHECKS == OFFER_EVENT_CHECKS
    assert _migration.STATUSES == JOINING_STATUSES == ("pending", "joined", "did_not_join")
    assert _migration.EVENTS == OFFER_EVENTS == ("created", "status", "revised", "letter", "joining", "joined", "did_not_join", "proof")
    columns = {c.name for c in JobOffer.__table__.columns}
    assert set(_migration.COLUMNS) <= columns
    assert all(JobOffer.__table__.c[name].nullable for name in _migration.COLUMNS)
    assert set(JOINING_CHECKS) <= {c.name for c in JobOffer.__table__.constraints}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec023_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)  # the real 0139 shape of `job_offers`
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _offer(url, status: str, application_status: str = "selected") -> uuid.UUID:
    app_id, offer_id, job_id = uuid.uuid4(), uuid.uuid4(), _job(url)
    _sql(
        url,
        "INSERT INTO job_applications (id, job_id, candidate_id, status, stage_changed_at, created_at, updated_at) VALUES (:id, :j, :c, :s, now(), now(), now())",
        {"id": app_id, "j": job_id, "c": _external(url, email=f"{app_id.hex[:10]}@example.com"), "s": application_status},
    )
    _sql(
        url,
        "INSERT INTO job_offers (id, application_id, offered_on, currency, status, created_at, updated_at) VALUES (:id, :a, current_date, 'INR', :s, now(), now())",
        {"id": offer_id, "a": app_id, "s": status},
    )
    return offer_id


def test_upgrade_backfills_the_joining_of_accepted_offers(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    joined = _offer(url, "accepted", "joined")
    waiting = _offer(url, "accepted")
    received = _offer(url, "offer_received")
    declined = _offer(url, "declined", "withdrawn")
    command.upgrade(cfg, HEAD)
    stored = dict(_sql(url, "SELECT id, joining_status FROM job_offers"))
    assert (stored[joined], stored[waiting], stored[received], stored[declined]) == ("joined", "pending", None, None)
    assert _sql(url, "SELECT count(*) FROM job_offer_events WHERE event IN ('joining', 'joined', 'did_not_join', 'proof')") == [(0,)]


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    offer = _offer(url, "accepted")
    with pytest.raises(Exception, match="ck_job_offers_joining_status"):
        _sql(url, "UPDATE job_offers SET joining_status = 'left' WHERE id = :id", {"id": offer})
    with pytest.raises(Exception, match="ck_job_offers_not_joined_reason"):
        _sql(url, "UPDATE job_offers SET joining_status = 'did_not_join' WHERE id = :id", {"id": offer})
    _sql(url, "UPDATE job_offers SET joining_status = 'did_not_join', not_joined_reason = 'Took another offer' WHERE id = :id", {"id": offer})
    _sql(url, "UPDATE job_offers SET joining_status = 'pending', not_joined_reason = NULL WHERE id = :id", {"id": offer})
    command.downgrade(cfg, BASE)
    assert "joining_status" not in {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'job_offers'")}
    with pytest.raises(Exception, match="ck_job_offer_events_event"):
        _sql(url, "INSERT INTO job_offer_events (id, offer_id, event, created_at) VALUES (:id, :o, 'proof', now())", {"id": uuid.uuid4(), "o": offer})
    command.upgrade(cfg, HEAD)
    _sql(url, "INSERT INTO job_offer_events (id, offer_id, event, created_at) VALUES (:id, :o, 'proof', now())", {"id": uuid.uuid4(), "o": offer})


def test_downgrade_refuses_while_joining_data_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    offer = _offer(url, "accepted")
    _sql(url, "UPDATE job_offers SET joining_status = 'pending', joining_location = 'Pune' WHERE id = :id", {"id": offer})
    _sql(url, "INSERT INTO job_offer_events (id, offer_id, event, created_at) VALUES (:id, :o, 'joining', now())", {"id": uuid.uuid4(), "o": offer})
    with pytest.raises(Exception, match="joining data exists"):
        command.downgrade(cfg, BASE)
