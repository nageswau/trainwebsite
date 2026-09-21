import importlib.util
import io
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CheckConstraint, CreateIndex

from app.models import SchoolStudentTransferRequest as Transfer

# ENH-005 spec §5.1: the request/history table. No database needed: the model is checked through its metadata and
# compiled DDL, and the migration by rendering its SQL offline (`alembic upgrade --sql` does the same).

MIGRATION = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0034_school_transfer_requests.py"


def test_table_shape_matches_the_spec():
    table = Transfer.__table__
    assert table.name == "school_student_transfer_requests"
    assert {"id", "school_student_id", "from_school_id", "to_school_id", "requested_by_user_id", "filed_by_school_id", "status", "reason",
            "decided_by_user_id", "decided_at", "decision_note", "outcome", "created_at", "updated_at"} <= set(table.c.keys())
    assert table.c.status.default.arg == "pending"
    checks = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
    assert {"ck_school_transfer_distinct_schools", "ck_school_transfer_filed_by_side"} <= checks
    indexed = {c.name for index in table.indexes for c in index.columns}
    assert {"school_student_id", "filed_by_school_id"} <= indexed


def test_at_most_one_pending_request_per_student_is_a_partial_unique_index():
    index = next(i for i in Transfer.__table__.indexes if i.name == "uq_school_transfer_pending_student")
    ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "CREATE UNIQUE INDEX uq_school_transfer_pending_student" in ddl
    assert "(school_student_id)" in ddl
    assert "WHERE status = 'pending'" in ddl


def _render_upgrade() -> str:
    spec = importlib.util.spec_from_file_location("migration_0034", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    buffer = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": buffer})
    with Operations.context(context):
        module.upgrade()
    return buffer.getvalue()


def test_the_migration_renders_the_same_table_index_and_checks():
    sql = _render_upgrade()
    assert "CREATE TABLE school_student_transfer_requests" in sql
    assert "CREATE UNIQUE INDEX uq_school_transfer_pending_student" in sql
    assert "WHERE status = 'pending'" in sql
    assert "ck_school_transfer_distinct_schools" in sql and "ck_school_transfer_filed_by_side" in sql
    assert "from_school_id <> to_school_id" in sql
    assert "filed_by_school_id IN (from_school_id, to_school_id)" in sql


def test_the_migration_is_additive_only():
    sql = _render_upgrade().upper()
    for forbidden in ("ALTER TABLE", "DROP ", "UPDATE ", "DELETE ", "INSERT "):
        assert forbidden not in sql
