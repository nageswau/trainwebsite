import importlib.util
import io
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.schema import CheckConstraint, UniqueConstraint

from app.models import SchoolActivityFeedback

# ENH-018 spec §4: one create-only table. Checked through metadata and an offline SQL render; no database needed.

MIGRATION = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0039_school_activity_feedback.py"


def _names(kind):
    return {c.name for c in SchoolActivityFeedback.__table__.constraints if isinstance(c, kind)}


def test_table_shape_matches_the_spec():
    assert SchoolActivityFeedback.__tablename__ == "school_activity_feedback"
    assert set(SchoolActivityFeedback.__table__.c.keys()) == {
        "id", "activity_id", "school_id", "submitted_by_user_id", "trainer_name", "rating", "satisfaction", "feedback", "suggestions", "created_at", "updated_at",
    }
    c = SchoolActivityFeedback.__table__.c
    assert not c.feedback.nullable and not c.rating.nullable and not c.satisfaction.nullable
    assert c.trainer_name.nullable and c.suggestions.nullable and c.trainer_name.type.length == 200


def test_one_feedback_per_activity_and_scores_are_checked_in_the_database():
    assert "uq_activity_feedback_activity" in _names(UniqueConstraint)
    assert {"ck_activity_feedback_rating", "ck_activity_feedback_satisfaction"} <= _names(CheckConstraint)


def _render(fn_name: str) -> str:
    spec = importlib.util.spec_from_file_location("migration_0039", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0039_school_activity_feedback" and module.down_revision == "0038_portfolio"
    buffer = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer})
    with Operations.context(context):
        getattr(module, fn_name)()
    return buffer.getvalue()


def test_migration_creates_only_the_new_table_and_touches_no_existing_row():
    sql = _render("upgrade")
    assert "CREATE TABLE school_activity_feedback" in sql
    for name in ("uq_activity_feedback_activity", "ck_activity_feedback_rating", "ck_activity_feedback_satisfaction"):
        assert name in sql
    assert "ALTER TABLE" not in sql and "UPDATE " not in sql and "DELETE " not in sql


def test_downgrade_drops_only_the_new_table():
    sql = _render("downgrade")
    dropped = {line.split("DROP TABLE ")[1].strip(" ;") for line in sql.splitlines() if "DROP TABLE" in line}
    assert dropped == {"school_activity_feedback"}
