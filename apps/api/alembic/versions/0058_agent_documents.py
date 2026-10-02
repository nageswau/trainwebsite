"""AGN-009 -- agency documents: student_documents owned by an agency record, document_requests, document_events.

Revision ID: 0058_agent_documents
Revises: 0057_agent_applications

docs/superpowers/specs/2026-10-02-agn-009-agent-documents-design.md §3 (DEC-SCOPE-051). Additive: `student_id` becomes nullable,
four nullable columns, one CHECK (every existing row already has `student_id`), two new tables. No existing row is read or written.
0001 builds a fresh database from the current models, which already carry all of this, so every add is guarded (0054's idiom).
downgrade() refuses while AGN-009 data exists rather than silently dropping it: an agency-only document would lose its only owner.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0058_agent_documents"
down_revision = "0057_agent_applications"
branch_labels = None
depends_on = None

TABLE = "student_documents"
OWNER_CHECK = "ck_student_documents_owner"
AGENT_INDEX = "ix_student_documents_agent_student_id"
FULFILS_UNIQUE = "uq_student_documents_fulfils_request_id"
NEW_COLUMNS = ("agent_student_id", "document_label", "uploaded_by_user_id", "fulfils_request_id")
UUID = postgresql.UUID(as_uuid=True)


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    tables = set() if inspector is None else set(inspector.get_table_names())
    if "document_requests" not in tables:
        op.create_table(
            "document_requests",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("agent_student_id", UUID, sa.ForeignKey("agent_students.id"), nullable=False),
            sa.Column("document_type", sa.String(80), nullable=False),
            sa.Column("document_label", sa.String(80), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="open"),
            sa.Column("requested_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("closed_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("status IN ('open', 'fulfilled', 'cancelled')", name="ck_document_requests_status"),
        )
        op.create_index("ix_document_requests_student_status", "document_requests", ["agent_student_id", "status"])

    existing = set() if inspector is None else {c["name"] for c in inspector.get_columns(TABLE)}
    op.alter_column(TABLE, "student_id", existing_type=UUID, nullable=True)
    if "agent_student_id" not in existing:
        op.add_column(TABLE, sa.Column("agent_student_id", UUID, sa.ForeignKey("agent_students.id"), nullable=True))
        op.create_index(AGENT_INDEX, TABLE, ["agent_student_id"])
    if "document_label" not in existing:
        op.add_column(TABLE, sa.Column("document_label", sa.String(80), nullable=True))
    if "uploaded_by_user_id" not in existing:
        op.add_column(TABLE, sa.Column("uploaded_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True))
    if "fulfils_request_id" not in existing:
        op.add_column(TABLE, sa.Column("fulfils_request_id", UUID, sa.ForeignKey("document_requests.id"), nullable=True))
        op.create_unique_constraint(FULFILS_UNIQUE, TABLE, ["fulfils_request_id"])
    checks = set() if inspector is None else {c["name"] for c in inspector.get_check_constraints(TABLE)}
    if OWNER_CHECK not in checks:
        op.create_check_constraint(OWNER_CHECK, TABLE, "student_id IS NOT NULL OR agent_student_id IS NOT NULL")

    if "document_events" not in tables:
        op.create_table(
            "document_events",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False, unique=True),
            sa.Column("document_id", UUID, sa.ForeignKey("student_documents.id"), nullable=True),
            sa.Column("request_id", UUID, sa.ForeignKey("document_requests.id"), nullable=True),
            sa.Column("event", sa.String(30), nullable=False),
            sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("from_status", sa.String(40), nullable=True),
            sa.Column("to_status", sa.String(40), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("file_key", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("document_id IS NOT NULL OR request_id IS NOT NULL", name="ck_document_events_subject"),
            sa.CheckConstraint(
                "event IN ('uploaded', 'replaced', 'verified', 'rejected', 'changes_required', 'requested', 'fulfilled', 'cancelled', 'downloaded')",
                name="ck_document_events_event",
            ),
        )
        op.create_index("ix_document_events_document_id", "document_events", ["document_id"])
        op.create_index("ix_document_events_request_id", "document_events", ["request_id"])


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        refusals = (
            (f"SELECT count(*) FROM {TABLE} WHERE agent_student_id IS NOT NULL OR student_id IS NULL", "agency documents exist"),
            ("SELECT count(*) FROM document_requests", "document requests exist"),
            ("SELECT count(*) FROM document_events", "document history exists"),
        )
        for sql, reason in refusals:
            if bind.execute(sa.text(sql)).scalar():
                raise RuntimeError(f"Refusing to downgrade 0058_agent_documents: {reason}")
    op.drop_table("document_events")
    op.drop_constraint(OWNER_CHECK, TABLE, type_="check")
    op.drop_constraint(FULFILS_UNIQUE, TABLE, type_="unique")
    op.drop_column(TABLE, "fulfils_request_id")
    op.drop_column(TABLE, "uploaded_by_user_id")
    op.drop_column(TABLE, "document_label")
    op.drop_index(AGENT_INDEX, table_name=TABLE)
    op.drop_column(TABLE, "agent_student_id")
    op.alter_column(TABLE, "student_id", existing_type=UUID, nullable=False)
    op.drop_table("document_requests")
