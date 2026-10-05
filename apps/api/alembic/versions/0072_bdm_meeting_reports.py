"""bdm-007 (DEC-SCOPE-070): meeting reports, a minimal task table (bdm-008 extends it), and the legacy backfill.

Every appointment completed under bdm-006 (outcome only) gets a read-only legacy report, and a follow-up for its stored
follow-up date, so "completed <=> one report" holds for every row. `bdm_appointments` is not altered.

Revision ID: 0072_bdm_meeting_reports
Revises: 0071_bdm_activities
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0072_bdm_meeting_reports"
down_revision = "0071_bdm_activities"
branch_labels = None
depends_on = None

REPORTS = "bdm_meeting_reports"
TASKS = "bdm_tasks"
TASK_KINDS = ("follow_up", "task")
TASK_SOURCES = ("appointment_outcome", "mou", "manual")
TASK_STATUSES = ("open", "done", "cancelled")

# Set-based and idempotent (NOT EXISTS), so it also runs when 0001's create_all already built the tables.
BACKFILL_REPORTS = f"""
INSERT INTO {REPORTS} (id, appointment_id, author_user_id, legacy, submitted_at, created_at, updated_at)
SELECT gen_random_uuid(), a.id, a.bdm_user_id, true, t.at, t.at, t.at
FROM bdm_appointments a
CROSS JOIN LATERAL (
    SELECT COALESCE(
        (SELECT max(e.created_at) FROM bdm_appointment_events e WHERE e.appointment_id = a.id AND e.to_status = 'completed'),
        a.updated_at
    ) AS at
) t
WHERE a.status = 'completed' AND NOT EXISTS (SELECT 1 FROM {REPORTS} r WHERE r.appointment_id = a.id)
"""
BACKFILL_FOLLOW_UPS = f"""
INSERT INTO {TASKS} (id, kind, title, due_on, organization_id, source, source_appointment_id, assignee_user_id, status)
SELECT gen_random_uuid(), 'follow_up', 'Follow up on ' || a.code, a.next_follow_up_on, a.organization_id, 'appointment_outcome',
       a.id, a.bdm_user_id, 'open'
FROM bdm_appointments a
WHERE a.status = 'completed' AND a.next_follow_up_on IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM {TASKS} t WHERE t.source_appointment_id = a.id)
"""


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid(name: str, *args, nullable: bool = False, **kwargs) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, nullable=nullable, **kwargs)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _create_tables() -> None:
    op.create_table(
        REPORTS,
        _uuid("id", primary_key=True),
        _uuid("appointment_id", sa.ForeignKey("bdm_appointments.id", ondelete="RESTRICT")),
        _uuid("author_user_id", sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("discussion", sa.String(4000), nullable=True),
        sa.Column("requirements", sa.String(2000), nullable=True),
        sa.Column("opportunity", sa.String(2000), nullable=True),
        sa.Column("next_action", sa.String(1000), nullable=True),
        sa.Column("responsible_person", sa.String(200), nullable=True),
        sa.Column("legacy", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("appointment_id", name="uq_bdm_meeting_reports_appointment"),
        sa.CheckConstraint("legacy OR discussion IS NOT NULL", name="ck_bdm_meeting_reports_discussion"),
    )
    op.create_table(
        TASKS,
        _uuid("id", primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        _uuid("organization_id", sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("source", sa.String(30), nullable=False),
        _uuid("source_appointment_id", sa.ForeignKey("bdm_appointments.id", ondelete="RESTRICT"), nullable=True),
        _uuid("assignee_user_id", sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("status", sa.String(20), server_default=sa.text("'open'"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("source_appointment_id", name="uq_bdm_tasks_source_appointment"),
        sa.CheckConstraint(_in("kind", TASK_KINDS), name="ck_bdm_tasks_kind"),
        sa.CheckConstraint(_in("source", TASK_SOURCES), name="ck_bdm_tasks_source"),
        sa.CheckConstraint(_in("status", TASK_STATUSES), name="ck_bdm_tasks_status"),
        sa.CheckConstraint("(source = 'appointment_outcome') = (source_appointment_id IS NOT NULL)", name="ck_bdm_tasks_source_link"),
        sa.CheckConstraint("(status = 'done') = (completed_at IS NOT NULL)", name="ck_bdm_tasks_completed"),
    )
    op.create_index("ix_bdm_tasks_assignee_status_due", TASKS, ["assignee_user_id", "status", "due_on"])


def upgrade() -> None:
    if op.get_context().as_sql or REPORTS not in sa.inspect(op.get_bind()).get_table_names():
        _create_tables()
    op.execute(BACKFILL_REPORTS)
    op.execute(BACKFILL_FOLLOW_UPS)


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {REPORTS} WHERE NOT legacy LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0072_bdm_meeting_reports: meeting reports exist. Remove them deliberately first.")
    op.drop_table(TASKS)  # legacy reports and their follow-ups are rebuilt from bdm_appointments on the next upgrade
    op.drop_table(REPORTS)
