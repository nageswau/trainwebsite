"""pob-026 -- client and candidate satisfaction surveys: `placement_surveys` (DEC-SCOPE-435 S2).

Revision ID: 0316_placement_surveys
Revises: 0314_vendor_bills

docs/superpowers/specs/2026-11-08-pob-026-satisfaction-survey-design.md. Additive only. 0001 builds a fresh database from the current models,
which already carry this table, so it is created only when missing. CHECKS is a frozen copy of `models.PLACEMENT_SURVEY_CHECKS`. No backfill:
the daily sweep writes the rows. The downgrade drops the table.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0316_placement_surveys"
down_revision = "0314_vendor_bills"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_placement_surveys_respondent": "respondent IN ('client', 'candidate')",
    "ck_placement_surveys_skip_reason": "skip_reason IS NULL OR skip_reason IN ('no_contact', 'no_email', 'no_sender')",
    "ck_placement_surveys_sent": "(sent_at IS NULL) = (skip_reason IS NOT NULL) AND (sent_at IS NULL) = (message_id IS NULL)",
    "ck_placement_surveys_resent": "(resent_at IS NULL) = (resend_message_id IS NULL) AND (resent_at IS NULL OR sent_at IS NOT NULL)",
    "ck_placement_surveys_client": "(respondent = 'client') = (contact_id IS NOT NULL) OR skip_reason IS NOT NULL",
    "ck_placement_surveys_rating": "(rating IS NULL) = (responded_at IS NULL) AND (rating IS NULL OR rating BETWEEN 1 AND 5)",
    "ck_placement_surveys_response": "responded_at IS NULL OR sent_at IS NOT NULL",
}
UUID = postgresql.UUID(as_uuid=True)


def _message(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("recruiter_messages.id", ondelete="RESTRICT"), nullable=True)


def upgrade() -> None:
    offline = op.get_context().as_sql
    if not offline and "placement_surveys" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "placement_surveys",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("placement_id", UUID, sa.ForeignKey("placements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("respondent", sa.String(10), nullable=False),
        sa.Column("contact_id", UUID, sa.ForeignKey("company_contacts.id", ondelete="RESTRICT"), nullable=True),
        _message("message_id"),
        _message("resend_message_id"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skip_reason", sa.String(16), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("comment", sa.String(1000), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("placement_id", "respondent", name="uq_placement_surveys_respondent"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )


def downgrade() -> None:
    op.drop_table("placement_surveys")
