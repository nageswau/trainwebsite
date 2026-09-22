import importlib.util
import io
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.schema import CheckConstraint, UniqueConstraint

from app.models import SchoolSkillAssessment, SchoolSkillAttendance, SchoolSkillBatch, SchoolSkillEnrollment, SchoolSkillScore, SchoolSkillSession

# ENH-011 spec §4: six create-only tables. No database needed: models are checked through their metadata, the migration by
# rendering its SQL offline (what `alembic upgrade --sql` does).

MIGRATION = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0035_school_skills.py"
TABLES = ["school_skill_batches", "school_skill_enrollments", "school_skill_sessions", "school_skill_attendance", "school_skill_assessments", "school_skill_scores"]


def _names(model, kind):
    return {c.name for c in model.__table__.constraints if isinstance(c, kind)}


@pytest.mark.parametrize(
    "model,table,columns",
    [
        (SchoolSkillBatch, "school_skill_batches", {"id", "school_id", "module_type", "title", "topic", "trainer_name", "start_date", "end_date", "status", "created_by_user_id", "created_at", "updated_at"}),
        (SchoolSkillEnrollment, "school_skill_enrollments", {"id", "batch_id", "school_student_id", "status", "completed_at", "certified_at", "enrolled_by_user_id", "created_at", "updated_at"}),
        (SchoolSkillSession, "school_skill_sessions", {"id", "batch_id", "session_date", "topic", "created_by_user_id", "created_at", "updated_at"}),
        (SchoolSkillAttendance, "school_skill_attendance", {"id", "session_id", "enrollment_id", "present", "marked_by_user_id", "created_at", "updated_at"}),
        (SchoolSkillAssessment, "school_skill_assessments", {"id", "batch_id", "name", "max_score", "created_by_user_id", "created_at", "updated_at"}),
        (SchoolSkillScore, "school_skill_scores", {"id", "assessment_id", "enrollment_id", "score", "remarks", "recorded_by_user_id", "created_at", "updated_at"}),
    ],
)
def test_table_shape_matches_the_spec(model, table, columns):
    assert model.__tablename__ == table
    assert set(model.__table__.c.keys()) == columns


def test_defaults_and_constraints():
    assert SchoolSkillBatch.__table__.c.status.default.arg == "open"
    assert SchoolSkillEnrollment.__table__.c.status.default.arg == "enrolled"
    assert {"ck_skill_batch_module", "ck_skill_batch_status", "ck_skill_batch_dates"} <= _names(SchoolSkillBatch, CheckConstraint)
    assert "ck_skill_enrollment_status" in _names(SchoolSkillEnrollment, CheckConstraint)
    assert "ck_skill_assessment_max" in _names(SchoolSkillAssessment, CheckConstraint)
    assert "ck_skill_score_nonneg" in _names(SchoolSkillScore, CheckConstraint)
    assert "uq_skill_enrollment_batch_student" in _names(SchoolSkillEnrollment, UniqueConstraint)
    assert "uq_skill_session_batch_date" in _names(SchoolSkillSession, UniqueConstraint)
    assert "uq_skill_attendance_session_enrollment" in _names(SchoolSkillAttendance, UniqueConstraint)
    assert "uq_skill_assessment_batch_name" in _names(SchoolSkillAssessment, UniqueConstraint)
    assert "uq_skill_score_assessment_enrollment" in _names(SchoolSkillScore, UniqueConstraint)


def _render(fn_name: str) -> str:
    spec = importlib.util.spec_from_file_location("migration_0035", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0035_school_skills" and module.down_revision == "0034_school_transfer_requests"
    buffer = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer})
    with Operations.context(context):
        getattr(module, fn_name)()
    return buffer.getvalue()


def test_migration_creates_the_six_tables_and_alters_nothing():
    sql = _render("upgrade")
    for table in TABLES:
        assert f"CREATE TABLE {table}" in sql
    for name in ("ck_skill_batch_module", "uq_skill_enrollment_batch_student", "uq_skill_session_batch_date", "uq_skill_score_assessment_enrollment"):
        assert name in sql
    assert "ALTER TABLE" not in sql and "UPDATE " not in sql and "DELETE " not in sql


def test_downgrade_drops_only_the_new_tables():
    sql = _render("downgrade")
    dropped = {line.split("DROP TABLE ")[1].strip(" ;") for line in sql.splitlines() if "DROP TABLE" in line}
    assert dropped == set(TABLES)
