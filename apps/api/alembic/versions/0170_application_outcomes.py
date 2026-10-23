"""ccrm-015 -- application exception outcomes: overseas_applications.outcome and application_outcomes.

Revision ID: 0170_application_outcomes
Revises: 0169_lead_next_action, 0169_overseas_student_notes

docs/superpowers/specs/2026-10-23-ccrm-015-application-outcomes-design.md (DEC-SCOPE-244). Also the merge point of main's two 0169 heads
(ccrm-003 and ccrm-010 both chained after 0168). Additive: NULL = no outcome. 0001 builds a fresh database from the current models, which
already carry both, so each is created only when missing (0168's idiom). O1 backfills `outcome = 'withdrawn'` on withdrawn rows.
downgrade() drops both (the withdrawn rows keep status 'withdrawn').
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0170_application_outcomes"
down_revision = ("0169_lead_next_action", "0169_overseas_student_notes")
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TABLE = "application_outcomes"
OUTCOMES = ("rejected", "withdrawn", "deferred", "on_hold", "offer_declined", "visa_refused")  # app/application_outcome.py


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IS NULL OR {column} IN ({', '.join(repr(v) for v in values)})"


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if inspector is None or "outcome" not in {c["name"] for c in inspector.get_columns("overseas_applications")}:
        op.add_column("overseas_applications", sa.Column("outcome", sa.String(20), nullable=True))
        op.create_check_constraint("ck_overseas_applications_outcome", "overseas_applications", _in("outcome", OUTCOMES))
    if inspector is None or TABLE not in inspector.get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("application_id", UUID, sa.ForeignKey("overseas_applications.id", ondelete="CASCADE"), nullable=False),
            sa.Column("outcome", sa.String(20), nullable=False),
            sa.Column("outcome_date", sa.Date(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("requested_by", sa.String(20), nullable=True),
            sa.Column("next_steps", sa.Text(), nullable=True),
            sa.Column("document_id", UUID, sa.ForeignKey("student_documents.id", ondelete="SET NULL"), nullable=True),
            sa.Column("previous_intake", sa.String(80), nullable=True),
            sa.Column("new_intake", sa.String(80), nullable=True),
            sa.Column("review_date", sa.Date(), nullable=True),
            sa.Column("hold_owner_id", UUID, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("another_offer_preferred", sa.Boolean(), nullable=True),
            sa.Column("created_by_id", UUID, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(_in("outcome", (*OUTCOMES, "cleared")), name="ck_application_outcomes_outcome"),
            sa.CheckConstraint(_in("requested_by", ("student", "counselor", "agent", "university")), name="ck_application_outcomes_requested_by"),
        )
        op.create_index("ix_application_outcomes_application_created", TABLE, ["application_id", "created_at"])
    op.execute("UPDATE overseas_applications SET outcome = 'withdrawn' WHERE status = 'withdrawn' AND outcome IS NULL")


def downgrade() -> None:
    op.drop_index("ix_application_outcomes_application_created", table_name=TABLE)
    op.drop_table(TABLE)
    op.drop_constraint("ck_overseas_applications_outcome", "overseas_applications", type_="check")
    op.drop_column("overseas_applications", "outcome")
