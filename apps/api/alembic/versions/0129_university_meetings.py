"""upc-009 -- University meetings.

Revision ID: 0129_university_meetings
Revises: 0128_university_milestones

docs/superpowers/specs/2026-10-09-upc-009-university-meetings-design.md §2 (DEC-SCOPE-144). Adds `university_meeting_code_seq`,
`university_meetings`, `university_meeting_participants` and `university_meeting_events`. 0001 builds a fresh database from the current
models, which already carry them, so each step is guarded. CHECKS repeats app.models (test_upc_009_migration). No backfill: existing
universities have no recorded meetings. downgrade() refuses while any meeting exists: it would drop meeting records and their history.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0129_university_meetings"
down_revision = "0128_university_milestones"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TYPES = (
    "'introduction', 'partnership_discussion', 'commercial_discussion', 'mou_discussion', 'product_presentation', "
    "'student_recruitment_discussion', 'application_process_discussion', 'marketing_discussion', 'university_visit', 'campus_visit', "
    "'webinar', 'training_session'"
)
CHECKS = {
    "ck_university_meetings_type": f"meeting_type IN ({TYPES})",
    "ck_university_meetings_mode": "mode IN ('online', 'offline')",
    "ck_university_meetings_status": "status IN ('scheduled', 'completed', 'cancelled')",
    "ck_university_meetings_completed": "(status = 'completed') = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL)",
    "ck_university_meetings_cancelled": "(status = 'cancelled') = (cancelled_at IS NOT NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL)",
    "ck_university_meetings_next_action": "(next_action IS NULL) = (next_action_due_on IS NULL)",
    "ck_university_meetings_outcome": ("status = 'completed' OR (discussion_points IS NULL AND decisions IS NULL AND next_action IS NULL AND next_meeting_date IS NULL)"),
    "ck_university_meeting_participants_one": "(contact_id IS NULL) <> (user_id IS NULL)",
    "ck_university_meeting_events_event": "event IN ('scheduled', 'edited', 'rescheduled', 'completed', 'cancelled')",
}
MEETING_CHECKS = [k for k in CHECKS if k.startswith("ck_university_meetings_")]


def _check(name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(CHECKS[name], name=name)


def _user_fk(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def _timestamp(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS university_meeting_code_seq")
    if not op.get_context().as_sql and "university_meetings" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "university_meetings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("university_id", UUID, sa.ForeignKey("universities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contact_id", UUID, sa.ForeignKey("university_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("contact_designation", sa.String(120), nullable=True),
        sa.Column("meeting_type", sa.String(40), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("meeting_url", sa.String(500), nullable=True),
        sa.Column("agenda", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("discussion_points", sa.Text(), nullable=True),
        sa.Column("decisions", sa.Text(), nullable=True),
        sa.Column("next_action", sa.String(200), nullable=True),
        sa.Column("next_action_due_on", sa.Date(), nullable=True),
        sa.Column("next_meeting_date", sa.Date(), nullable=True),
        _user_fk("responsible_user_id"),
        _user_fk("created_by_user_id"),
        sa.Column("status", sa.String(12), nullable=False, server_default="scheduled"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _user_fk("completed_by_user_id", nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.UniqueConstraint("code", name="uq_university_meetings_code"),
        *(_check(name) for name in MEETING_CHECKS),
    )
    op.create_index("ix_university_meetings_university_starts", "university_meetings", ["university_id", "starts_at"])
    op.create_index("ix_university_meetings_status_starts", "university_meetings", ["status", "starts_at"])
    op.create_index("ix_university_meetings_responsible", "university_meetings", ["responsible_user_id"])
    op.create_table(
        "university_meeting_participants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("meeting_id", UUID, sa.ForeignKey("university_meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", UUID, sa.ForeignKey("university_contacts.id", ondelete="CASCADE"), nullable=True),
        _user_fk("user_id", nullable=True),
        _check("ck_university_meeting_participants_one"),
        sa.UniqueConstraint("meeting_id", "contact_id", name="uq_university_meeting_participants_contact"),
        sa.UniqueConstraint("meeting_id", "user_id", name="uq_university_meeting_participants_user"),
    )
    op.create_table(
        "university_meeting_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("meeting_id", UUID, sa.ForeignKey("university_meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event", sa.String(12), nullable=False),
        sa.Column("old_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        _user_fk("actor_user_id"),
        sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        _timestamp("created_at"),
        _check("ck_university_meeting_events_event"),
    )
    op.create_index("ix_university_meeting_events_meeting", "university_meeting_events", ["meeting_id", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM university_meetings LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0129_university_meetings: university meetings exist. Remove them deliberately first.")
    op.drop_table("university_meeting_events")
    op.drop_table("university_meeting_participants")
    op.drop_table("university_meetings")
    op.execute("DROP SEQUENCE IF EXISTS university_meeting_code_seq")
