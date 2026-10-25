"""ccrm-004 -- counselor meetings on a lead and appointment outcome notes: lead_meetings, appointments.outcome_notes.

Revision ID: 0181_lead_meetings
Revises: 0180_application_checklists

docs/superpowers/specs/2026-10-25-ccrm-004-counselor-lead-activities-design.md (DEC-SCOPE-259 LG3, LG4). Additive: no existing row changes.
0001 builds a fresh database from the current models, which already carry both, so each is created only when missing (0167's idiom).
downgrade() refuses while meetings or outcome notes exist: lead history is not dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0181_lead_meetings"
down_revision = "0180_application_checklists"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TABLE = "lead_meetings"
MAX = 2000  # app.models.LEAD_MEETING_NOTES_MAX
MODES = ("Online", "Phone", "In person")  # app.models.APPOINTMENT_MODES


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    if offline or TABLE not in inspector.get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("lead_id", UUID, sa.ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("author_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("mode", sa.String(40), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("mode IN ({})".format(", ".join(f"'{m}'" for m in MODES)), name="ck_lead_meetings_mode"),
            sa.CheckConstraint(f"length(notes) BETWEEN 1 AND {MAX}", name="ck_lead_meetings_notes"),
        )
        op.create_index("ix_lead_meetings_lead_occurred", TABLE, ["lead_id", "occurred_at"])
    if offline or "outcome_notes" not in {c["name"] for c in inspector.get_columns("appointments")}:
        op.add_column("appointments", sa.Column("outcome_notes", sa.Text(), nullable=True))


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        if bind.execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0181: lead meetings exist (ccrm-004)")
        if bind.execute(sa.text("SELECT 1 FROM appointments WHERE outcome_notes IS NOT NULL LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0181: appointment outcome notes exist (ccrm-004)")
    op.drop_column("appointments", "outcome_notes")
    op.drop_index("ix_lead_meetings_lead_occurred", table_name=TABLE)
    op.drop_table(TABLE)
