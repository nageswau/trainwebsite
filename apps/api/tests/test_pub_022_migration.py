"""PUB-022 -- migration 0158_social_proof (spec §3). Round trip runs in a throwaway database (the upc-023 pattern)."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_pub_022_migration_0158", VERSIONS / "0158_social_proof.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0157_direct_tieups", "0158_social_proof"
NEW_COLUMNS = {"published", "featured", "display_order", "context", "consent_confirmed", "consent_by_user_id", "consent_at", "photo_key", "photo_content_type"}


def test_migration_chains_after_0157_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import RATING_BADGE_CHECKS, TESTIMONIAL_CHECKS, SiteRatingBadge, Testimonial

    assert TESTIMONIAL_CHECKS == _migration.TESTIMONIAL_CHECKS
    assert RATING_BADGE_CHECKS == _migration.BADGE_CHECKS
    assert set(_migration.COLUMNS) == NEW_COLUMNS <= {c.name for c in Testimonial.__table__.columns}
    for table, checks in ((Testimonial.__table__, TESTIMONIAL_CHECKS), (SiteRatingBadge.__table__, RATING_BADGE_CHECKS)):
        by_name = {c.name: str(c.sqltext) for c in table.constraints if getattr(c, "sqltext", None) is not None}
        for name, sql in checks.items():
            assert by_name[name] == sql


@pytest.mark.asyncio
async def test_schema_exists_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns, checks, has_badge = await conn.run_sync(lambda s: (
        {c["name"] for c in inspect(s).get_columns("testimonials")},
        {c["name"] for c in inspect(s).get_check_constraints("testimonials")},
        inspect(s).has_table("site_rating_badge"),
    ))
    assert NEW_COLUMNS <= columns and set(_migration.TESTIMONIAL_CHECKS) <= checks and has_badge


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"pub022_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _testimonial(url: str, division: str = "it") -> str:
    tid = str(uuid.uuid4())
    _sql(url, "INSERT INTO testimonials (id, division, person_name, headline, quote, rating) VALUES (:i, :d, 'A', 'H', 'Q', 5)", {"i": tid, "d": division})
    return tid


def test_round_trip_unpublishes_existing_rows(isolated_db):
    url = isolated_db["url"]
    tid = _testimonial(url)
    command.upgrade(isolated_db["cfg"], HEAD)
    assert _sql(url, "SELECT published, featured, consent_confirmed FROM testimonials WHERE id = :i", {"i": tid}) == [(False, False, False)]
    assert _sql(url, "SELECT to_regclass('site_rating_badge') IS NOT NULL")[0][0]
    command.downgrade(isolated_db["cfg"], BASE)
    rows = _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'testimonials'")
    assert not (NEW_COLUMNS & {r[0] for r in rows})
    assert not _sql(url, "SELECT to_regclass('site_rating_badge') IS NOT NULL")[0][0]


def test_upgrade_refuses_an_unknown_division(isolated_db):
    _testimonial(isolated_db["url"], division="school")
    with pytest.raises(RuntimeError, match="has division 'school'"):
        command.upgrade(isolated_db["cfg"], HEAD)


@pytest.mark.parametrize(
    ("assignment", "constraint"),
    [
        ("published = true", "ck_testimonials_publish_needs_consent"),
        ("rating = 0", "ck_testimonials_rating_range"),
        ("rating = 6", "ck_testimonials_rating_range"),
        ("division = 'school'", "ck_testimonials_division"),
    ],
)
def test_testimonial_checks(isolated_db, assignment, constraint):
    url = isolated_db["url"]
    command.upgrade(isolated_db["cfg"], HEAD)
    tid = _testimonial(url)
    with pytest.raises(Exception, match=constraint):
        _sql(url, f"UPDATE testimonials SET {assignment} WHERE id = :i", {"i": tid})
    _sql(url, "UPDATE testimonials SET consent_confirmed = true, published = true WHERE id = :i", {"i": tid})


@pytest.mark.parametrize(
    ("values", "constraint"),
    [("2, 'Google', 4.8, 10", "ck_site_rating_badge_single"), ("1, 'Google', 5.5, 10", "ck_site_rating_badge_rating"), ("1, 'Google', 4.8, -1", "ck_site_rating_badge_count")],
)
def test_badge_checks(isolated_db, values, constraint):
    url = isolated_db["url"]
    command.upgrade(isolated_db["cfg"], HEAD)
    with pytest.raises(Exception, match=constraint):
        _sql(url, f"INSERT INTO site_rating_badge (id, source_name, rating, review_count, as_of) VALUES ({values}, '2026-10-01')")
    _sql(url, "INSERT INTO site_rating_badge (id, source_name, rating, review_count, as_of) VALUES (1, 'Google', 4.8, 10, '2026-10-01')")
