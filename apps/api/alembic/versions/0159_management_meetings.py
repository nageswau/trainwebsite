"""mgmt-029 -- management meetings + minutes chain: management_meetings, management_meeting_participants and
management_discussions.meeting_id.

Revision ID: 0159_management_meetings
Revises: 0158_social_proof

docs/superpowers/specs/2026-10-14-mgmt-029-management-meetings-design.md §3. Two new tables and one nullable column; no existing row
changes (every discussion keeps meeting_id null). 0001 builds a fresh database from the current models, which already carry them, so
each step runs only when missing (0122's idiom). downgrade() refuses while any meeting exists: minutes are never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0159_management_meetings"
down_revision = "0158_social_proof"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
# Frozen copies of app.models.MEETING_KINDS / MEETING_STATUSES / APPOINTMENT_MODES.
KINDS = ("partner", "department", "school", "university", "agent", "recruiter", "marketing_review")
STATUSES = ("scheduled", "completed", "cancelled")
MODES = ("Online", "Phone", "In person")


def _user(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else set(inspector.get_table_names())
    if "management_meetings" not in existing:
        op.create_table(
            "management_meetings",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("mode", sa.String(12), nullable=False),
            sa.Column("location", sa.String(200), nullable=True),
            sa.Column("meeting_url", sa.String(500), nullable=True),
            sa.Column("agenda", sa.Text(), nullable=True),
            sa.Column("minutes", sa.Text(), nullable=True),
            sa.Column("minutes_recorded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(12), server_default=sa.text("'scheduled'"), nullable=False),
            _user("created_by_user_id"),
            _user("updated_by_user_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(_in("kind", KINDS), name="ck_management_meetings_kind"),
            sa.CheckConstraint(_in("status", STATUSES), name="ck_management_meetings_status"),
            sa.CheckConstraint(_in("mode", MODES), name="ck_management_meetings_mode"),
        )
        op.create_index("ix_management_meetings_starts_at", "management_meetings", ["starts_at"])
        op.create_index("ix_management_meetings_status_starts_at", "management_meetings", ["status", "starts_at"])
    if "management_meeting_participants" not in existing:
        op.create_table(
            "management_meeting_participants",
            sa.Column("meeting_id", UUID, sa.ForeignKey("management_meetings.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        )
        op.create_index("ix_management_meeting_participants_user", "management_meeting_participants", ["user_id"])
    columns = set() if offline else {c["name"] for c in inspector.get_columns("management_discussions")}
    if "meeting_id" not in columns:
        op.add_column("management_discussions", sa.Column("meeting_id", UUID, sa.ForeignKey("management_meetings.id", ondelete="RESTRICT"), nullable=True))
        op.create_index("ix_management_discussions_meeting_id", "management_discussions", ["meeting_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM management_meetings LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0159_management_meetings: meetings exist. Clear them deliberately first.")
    op.drop_index("ix_management_discussions_meeting_id", table_name="management_discussions")
    op.drop_column("management_discussions", "meeting_id")
    op.drop_table("management_meeting_participants")
    op.drop_table("management_meetings")
