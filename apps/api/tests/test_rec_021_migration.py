"""rec-021 -- migration 0146_interview_feedback (spec §1). Round trip, constraints and downgrade refusal run in a throwaway database built
from scratch (the tel-002 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
asyncio.run()."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_rec_018_migration import _application
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_021_migration_0146", VERSIONS / "0146_interview_feedback.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0145_university_onboarding", "0146_interview_feedback"


def test_migration_chains_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(HEAD) <= 32  # alembic_version.version_num is VARCHAR(32)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import FEEDBACK_CHECKS, InterviewFeedback

    assert _migration.CHECKS == FEEDBACK_CHECKS  # one source of truth for the CHECK text
    table = InterviewFeedback.__table__
    assert {c.name for c in table.columns} == {
        "interview_id",
        "technical_rating",
        "communication_rating",
        "overall_rating",
        "strengths",
        "weaknesses",
        "recruiter_comments",
        "company_feedback",
        "next_round",
        "final_decision",
        "recorded_by_user_id",
        "created_at",
        "updated_at",
    }
    assert set(FEEDBACK_CHECKS) <= {c.name for c in table.constraints}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec021_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        # 0001's create_all builds today's models (this table included); going to head and back down gives the real 0145 shape.
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _interview(url) -> tuple[uuid.UUID, uuid.UUID]:
    user_id, application_id = _application(url)
    interview_id = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO interviews (id, application_id, scheduled_at, mode, status, created_at, updated_at) VALUES (:id, :a, now(), 'Online', 'completed', now(), now())",
        {"id": interview_id, "a": application_id},
    )
    return user_id, interview_id


INSERT = (
    "INSERT INTO interview_feedback (interview_id, overall_rating, technical_rating, communication_rating, next_round, final_decision, "
    "recorded_by_user_id) VALUES (:i, :overall, :tech, :comm, :next, :decision, :u)"
)


def _row(url, user_id, interview_id, *, overall=4, tech=None, comm=None, next=None, decision=None):
    _sql(url, INSERT, {"i": interview_id, "overall": overall, "tech": tech, "comm": comm, "next": next, "decision": decision, "u": user_id})


def test_round_trip_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    user_id, interview_id = _interview(url)
    for kwargs, check in (
        ({"overall": 6}, "ck_interview_feedback_overall"),
        ({"overall": 0}, "ck_interview_feedback_overall"),
        ({"tech": 6}, "ck_interview_feedback_technical"),
        ({"comm": 0}, "ck_interview_feedback_communication"),
        ({"next": "lunch_round"}, "ck_interview_feedback_next_round"),
        ({"decision": "maybe"}, "ck_interview_feedback_decision"),
        ({"decision": "rejected", "next": "manager_round"}, "ck_interview_feedback_rejected_no_next"),
    ):
        with pytest.raises(Exception, match=check):
            _row(url, user_id, interview_id, **kwargs)
    with pytest.raises(Exception, match="overall_rating"):
        _row(url, user_id, interview_id, overall=None)
    _row(url, user_id, interview_id, overall=5, tech=1, comm=5, next="manager_round", decision="selected")
    with pytest.raises(Exception, match="pkey"):
        _row(url, user_id, interview_id)  # one current feedback per interview (FB1)
    with pytest.raises(Exception, match="feedback exists"):
        command.downgrade(cfg, BASE)
