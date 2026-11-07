"""pob-007 -- BD activity completeness: LinkedIn messages, message outcomes, call details, meeting details and action items, follow-up
priority and reminder, and the `company_visit` meeting type.

Revision ID: 0301_bd_activity
Revises: 0300_vendor_master

docs/superpowers/specs/2026-11-07-pob-007-bd-activity-design.md (DEC-SCOPE-421). 0001 builds a fresh database from the current models, which already
carry all of this, so each column and table is added only when missing (0299's idiom); the checks are dropped and re-created, frozen copies of the
models at this revision. The upgrade changes no existing row (`priority` fills with its default). The downgrade deletes LinkedIn messages (the old
channel check cannot hold them) and turns `company_visit` meetings into `company_meeting`, so no meeting is lost.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0301_bd_activity"
down_revision = "0300_vendor_master"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
OLD_TYPES = (
    "'company_meeting', 'hr_meeting', 'requirement_discussion', 'recruitment_presentation', 'contract_discussion', "
    "'campus_recruitment_discussion', 'placement_drive_discussion'"
)
CHECKS = {  # frozen copies of the models at this revision (test_pob_007_migration keeps them identical)
    "recruiter_messages": {
        "ck_recruiter_messages_channel": "channel IN ('whatsapp', 'email', 'linkedin')",
        "ck_recruiter_messages_linkedin": (
            "(channel = 'linkedin') = (linkedin_action IS NOT NULL) AND (linkedin_action IS NULL OR linkedin_action IN ('connection_request', 'message'))"
        ),
    },
    "recruiter_calls": {"ck_recruiter_calls_job": "job_id IS NULL OR contact_id IS NOT NULL"},
    "recruiter_meetings": {"ck_recruiter_meetings_type": f"meeting_type IN ({OLD_TYPES}, 'company_visit')"},
    "recruiter_follow_ups": {
        "ck_recruiter_follow_ups_priority": "priority IN ('high', 'medium', 'low')",
        "ck_recruiter_follow_ups_remind": "remind_at IS NULL OR remind_at <= due_at",
    },
}
OLD_CHECKS = {
    "recruiter_messages": {"ck_recruiter_messages_channel": "channel IN ('whatsapp', 'email')"},
    "recruiter_meetings": {"ck_recruiter_meetings_type": f"meeting_type IN ({OLD_TYPES})"},
}
COLUMNS = {
    "recruiter_messages": (
        sa.Column("linkedin_action", sa.String(24), nullable=True),
        sa.Column("outcome", sa.String(500), nullable=True),
        sa.Column("follow_up_id", UUID, sa.ForeignKey("recruiter_follow_ups.id", ondelete="RESTRICT"), nullable=True),
    ),
    "recruiter_calls": (
        sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("objections", sa.JSON(), nullable=True),
        sa.Column("objection_notes", sa.String(1000), nullable=True),
        sa.Column("next_action", sa.String(500), nullable=True),
    ),
    "recruiter_meetings": (sa.Column("hiring_forecast", sa.JSON(), nullable=True), sa.Column("commercial_notes", sa.Text(), nullable=True)),
    "recruiter_follow_ups": (
        sa.Column("priority", sa.String(8), server_default=sa.text("'medium'"), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=True),
    ),
}
ACTION_ITEMS = "recruiter_meeting_action_items"


def _set_checks(checks: dict[str, dict[str, str]]) -> None:
    for table, items in checks.items():
        for name, sql in items.items():
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
            op.create_check_constraint(name, table, sql)


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    for table, columns in COLUMNS.items():
        present = set() if offline else {c["name"] for c in inspector.get_columns(table)}
        for column in columns:
            if column.name not in present:
                op.add_column(table, column.copy())
    if offline or ACTION_ITEMS not in inspector.get_table_names():
        op.create_table(
            ACTION_ITEMS,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("meeting_id", UUID, sa.ForeignKey("recruiter_meetings.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("follow_up_id", UUID, sa.ForeignKey("recruiter_follow_ups.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.UniqueConstraint("meeting_id", "position", name="uq_recruiter_meeting_action_items_position"),
            sa.UniqueConstraint("follow_up_id", name="uq_recruiter_meeting_action_items_follow_up"),
        )
    _set_checks(CHECKS)


def downgrade() -> None:
    op.drop_table(ACTION_ITEMS)
    op.execute("DELETE FROM recruiter_messages WHERE channel = 'linkedin'")
    op.execute("UPDATE recruiter_meetings SET meeting_type = 'company_meeting' WHERE meeting_type = 'company_visit'")
    for table, items in CHECKS.items():
        for name in items:
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    for table, columns in COLUMNS.items():
        for column in columns:
            op.drop_column(table, column.name)
    _set_checks(OLD_CHECKS)
