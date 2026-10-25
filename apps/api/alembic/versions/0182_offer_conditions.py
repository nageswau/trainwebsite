"""ccrm-024 -- an offer's conditions (application_offer_conditions).

Revision ID: 0182_offer_conditions
Revises: 0181_lead_meetings

docs/superpowers/specs/2026-10-25-ccrm-024-offer-conditions-design.md (DEC-SCOPE-260). Each offer's free-text conditions become one open
condition owned by the student (C1), on every offer status so the history stays faithful; blank text makes none. 0001 builds a fresh
database from the current models, so the table is made only when missing (0166's idiom) and the backfill then finds nothing to copy twice.
OWNERS / STATUSES repeat app.models (test_ccrm_024_migration). The downgrade drops the table.
"""

import sqlalchemy as sa

from alembic import op

revision = "0182_offer_conditions"
down_revision = "0181_lead_meetings"
branch_labels = None
depends_on = None

TABLE = "application_offer_conditions"
OWNERS = ("student", "counselor", "agent")
STATUSES = ("open", "met", "waived", "failed")
BACKFILL = f"""
INSERT INTO {TABLE} (id, offer_id, description, owner, status, created_at, updated_at)
SELECT gen_random_uuid(), o.id, btrim(o.conditions), 'student', 'open', now(), now()
FROM application_offers o
WHERE btrim(coalesce(o.conditions, '')) <> ''
  AND NOT EXISTS (SELECT 1 FROM {TABLE} c WHERE c.offer_id = o.id)
"""


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    if inspector is None or TABLE not in inspector.get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("offer_id", sa.Uuid(), sa.ForeignKey("application_offers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("owner", sa.String(20), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'open'")),
            sa.Column("evidence_document_id", sa.Uuid(), sa.ForeignKey("student_documents.id", ondelete="SET NULL"), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(_in("owner", OWNERS), name="ck_application_offer_conditions_owner"),
            sa.CheckConstraint(_in("status", STATUSES), name="ck_application_offer_conditions_status"),
        )
        op.create_index("ix_application_offer_conditions_offer_id", TABLE, ["offer_id"])
    op.execute(BACKFILL)


def downgrade() -> None:
    op.drop_table(TABLE)
