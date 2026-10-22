"""ccrm-002 -- append-only lead notes: lead_notes.

Revision ID: 0167_lead_notes
Revises: 0166_application_codes

docs/superpowers/specs/2026-10-22-ccrm-002-lead-notes-design.md (DEC-SCOPE-242). Additive: no existing row changes. 0001 builds a fresh
database from the current models, which already carry the table, so it is created only when missing (0166's idiom). downgrade() refuses
while notes exist: lead history is not dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0167_lead_notes"
down_revision = "0166_application_codes"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TABLE = "lead_notes"
MAX = 4000  # app.models.LEAD_NOTE_MAX


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("lead_id", UUID, sa.ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("author_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"length(body) BETWEEN 1 AND {MAX}", name="ck_lead_notes_body"),
    )
    op.create_index("ix_lead_notes_lead_created", TABLE, ["lead_id", "created_at"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0167: lead notes exist (ccrm-002)")
    op.drop_index("ix_lead_notes_lead_created", table_name=TABLE)
    op.drop_table(TABLE)
