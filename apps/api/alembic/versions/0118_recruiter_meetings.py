"""rec-028 -- recruiter_meetings + recruiter_meeting_participants + recruiter_meeting_events + recruiter_meeting_code_seq.

Revision ID: 0118_recruiter_meetings
Revises: 0117_job_descriptions

docs/superpowers/specs/2026-10-08-rec-028-company-meetings-design.md §2 (DEC-SCOPE-133). New tables only; no existing row changes. 0001
builds a fresh database from the current models, which already carry these tables, so they are created only when missing (0116's idiom).
CHECKS repeats app.models.RECRUITER_MEETING_CHECKS (test_rec_028_migration). downgrade() refuses while any meeting exists: entered data is
never dropped silently.

Re-chained 2026-10-08 on merging `main` @ `09abb21e`: drafted as `0117_recruiter_meetings` (DEC-SCOPE-132, API §12AZ, RBAC §2.58) on
`0116_recruiter_follow_ups`, but rec-008 (`0117_job_descriptions`) merged first and took those numbers, so this is `0118` (DEC-SCOPE-133,
API §12BA, RBAC §2.59). A database stamped at the draft is re-stamped with `alembic stamp --purge 0116_recruiter_follow_ups`, then
`upgrade head` (the table step is guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0118_recruiter_meetings"
down_revision = "0117_job_descriptions"
branch_labels = None
depends_on = None

MEETINGS, PARTICIPANTS, EVENTS = "recruiter_meetings", "recruiter_meeting_participants", "recruiter_meeting_events"
SEQ = "recruiter_meeting_code_seq"
UUID = postgresql.UUID(as_uuid=True)
TYPES = ("company_meeting", "hr_meeting", "requirement_discussion", "recruitment_presentation", "contract_discussion",
         "campus_recruitment_discussion", "placement_drive_discussion")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {  # must equal app.models.RECRUITER_MEETING_CHECKS (test_rec_028_migration)
    "ck_recruiter_meetings_type": _in("meeting_type", TYPES),
    "ck_recruiter_meetings_mode": _in("mode", ("Online", "Phone", "In person")),
    "ck_recruiter_meetings_status": _in("status", ("scheduled", "completed", "cancelled")),
    "ck_recruiter_meetings_state": (
        "(status = 'completed') = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL) "
        "AND (completed_at IS NULL) = (outcome IS NULL) AND (status = 'cancelled') = (cancelled_at IS NOT NULL) "
        "AND (cancelled_at IS NULL) = (cancel_reason IS NULL) AND (status = 'completed' OR (next_action IS NULL AND follow_up_id IS NULL))"
    ),
    "ck_recruiter_meeting_participants_one": "(contact_id IS NULL) <> (user_id IS NULL)",
    "ck_recruiter_meeting_events_event": _in("event", ("scheduled", "rescheduled", "completed", "cancelled")),
}
INDEXES = {
    "ix_recruiter_meetings_company_starts": (MEETINGS, ["company_id", "starts_at"]),
    "ix_recruiter_meetings_status_starts": (MEETINGS, ["status", "starts_at"]),
    "ix_recruiter_meetings_contact": (MEETINGS, ["contact_id"]),
    "ix_recruiter_meeting_events_meeting": (EVENTS, ["meeting_id", "position"]),
}


def _checks(prefix: str):
    return [sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items() if name.startswith(prefix)]


def upgrade() -> None:
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}")
    if not op.get_context().as_sql and MEETINGS in sa.inspect(op.get_bind()).get_table_names():
        return
    when = sa.DateTime(timezone=True)

    def fk(target: str):
        return sa.ForeignKey(target, ondelete="RESTRICT")

    op.create_table(
        MEETINGS,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("meeting_code", sa.String(20), nullable=False),
        sa.Column("company_id", UUID, fk("companies.id"), nullable=False),
        sa.Column("contact_id", UUID, fk("company_contacts.id"), nullable=True),
        sa.Column("meeting_type", sa.String(40), nullable=False),
        sa.Column("starts_at", when, nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("meeting_url", sa.String(500), nullable=True),
        sa.Column("purpose", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'scheduled'")),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("next_action", sa.String(500), nullable=True),
        sa.Column("follow_up_id", UUID, fk("recruiter_follow_ups.id"), nullable=True),
        sa.Column("completed_at", when, nullable=True),
        sa.Column("completed_by_user_id", UUID, fk("users.id"), nullable=True),
        sa.Column("cancelled_at", when, nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.Column("created_by_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("created_at", when, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", when, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("meeting_code", name="uq_recruiter_meetings_code"),
        *_checks("ck_recruiter_meetings_"),
    )
    op.create_table(
        PARTICIPANTS,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("meeting_id", UUID, fk("recruiter_meetings.id"), nullable=False),
        sa.Column("contact_id", UUID, fk("company_contacts.id"), nullable=True),
        sa.Column("user_id", UUID, fk("users.id"), nullable=True),
        sa.UniqueConstraint("meeting_id", "contact_id", name="uq_recruiter_meeting_participants_contact"),
        sa.UniqueConstraint("meeting_id", "user_id", name="uq_recruiter_meeting_participants_user"),
        *_checks("ck_recruiter_meeting_participants_"),
    )
    op.create_table(
        EVENTS,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("meeting_id", UUID, fk("recruiter_meetings.id"), nullable=False),
        sa.Column("event", sa.String(16), nullable=False),
        sa.Column("old_starts_at", when, nullable=True),
        sa.Column("new_starts_at", when, nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("actor_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", when, server_default=sa.func.now(), nullable=False),
        *_checks("ck_recruiter_meeting_events_"),
    )
    for name, (table, columns) in INDEXES.items():
        op.create_index(name, table, columns)


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {MEETINGS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0118_recruiter_meetings: recruiter meetings exist. Clear them deliberately first.")
    op.drop_table(EVENTS)
    op.drop_table(PARTICIPANTS)
    op.drop_table(MEETINGS)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
