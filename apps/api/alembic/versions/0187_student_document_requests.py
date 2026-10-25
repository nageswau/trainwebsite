"""ccrm-020 -- document requests for direct students: document_requests.student_user_id, application_id, checklist_item_id, due_date; a
nullable agent_student_id with the owner CHECK (an agency record or a student login, exactly one); the student and open-due indexes.

Revision ID: 0187_student_document_requests
Revises: 0186_lead_loss_capture

docs/superpowers/specs/2026-10-25-ccrm-020-document-requests-design.md (DEC-SCOPE-265). Existing rows are all agency requests, so the
CHECK holds without a backfill. 0001 builds a fresh database from the current models, which already carry the columns and constraints,
so each step runs only when missing (0166's idiom). The downgrade is lossy: a direct student's requests, their events and the documents'
links to them go before agent_student_id is NOT NULL again.
"""

import sqlalchemy as sa

from alembic import op

revision = "0187_student_document_requests"
down_revision = "0186_lead_loss_capture"
branch_labels = None
depends_on = None

TABLE = "document_requests"
OWNER_CHECK = "ck_document_requests_owner"
STUDENT_INDEX, DUE_INDEX = "ix_document_requests_student_user_status", "ix_document_requests_open_due"
STUDENT_ROWS = f"SELECT id FROM {TABLE} WHERE student_user_id IS NOT NULL"


def _has_column(name: str) -> bool:
    return not op.get_context().as_sql and name in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _has_check(name: str) -> bool:
    return not op.get_context().as_sql and name in {c["name"] for c in sa.inspect(op.get_bind()).get_check_constraints(TABLE)}


def upgrade() -> None:
    for column in (
        sa.Column("student_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("overseas_applications.id"), nullable=True),
        sa.Column("checklist_item_id", sa.Uuid(), sa.ForeignKey("application_checklist_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
    ):
        if not _has_column(column.name):
            op.add_column(TABLE, column)
    op.alter_column(TABLE, "agent_student_id", nullable=True)
    if not _has_check(OWNER_CHECK):
        op.create_check_constraint(OWNER_CHECK, TABLE, "(agent_student_id IS NULL) <> (student_user_id IS NULL)")
    op.execute(f"CREATE INDEX IF NOT EXISTS {STUDENT_INDEX} ON {TABLE} (student_user_id, status)")
    op.execute(f"CREATE INDEX IF NOT EXISTS {DUE_INDEX} ON {TABLE} (due_date) WHERE status = 'open' AND due_date IS NOT NULL")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {DUE_INDEX}")
    op.execute(f"DROP INDEX IF EXISTS {STUDENT_INDEX}")
    op.execute(f"UPDATE student_documents SET fulfils_request_id = NULL WHERE fulfils_request_id IN ({STUDENT_ROWS})")
    op.execute(f"DELETE FROM document_events WHERE request_id IN ({STUDENT_ROWS})")
    op.execute(f"DELETE FROM {TABLE} WHERE student_user_id IS NOT NULL")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {OWNER_CHECK}")
    op.alter_column(TABLE, "agent_student_id", nullable=False)
    for name in ("due_date", "checklist_item_id", "application_id", "student_user_id"):
        op.drop_column(TABLE, name)
