"""pob-022 -- interview coordination automation (DEC-SCOPE-421 A2-A7).

Revision ID: 0301_interview_automation
Revises: 0300_vendor_master

docs/superpowers/specs/2026-11-07-pob-022-interview-automation-design.md. On `interviews`: the two reminder markers, the feedback chase's
follow-up and its escalation time. New `interview_automation_settings` (one row, id 1, seeded with the defaults). A7: interviews that already
started, or start within a day, have their reminders stamped, and interviews that already started have their chase stamped as handled, so
the first sweeps send no backlog.

Every step is guarded, because 0001's `create_all` already builds today's models on a fresh database. The checks are frozen copies of
`models.INTERVIEW_AUTOMATION_CHECKS`.
"""

import sqlalchemy as sa

from alembic import op

revision = "0301_interview_automation"
down_revision = "0300_vendor_master"
branch_labels = None
depends_on = None

TABLE = "interview_automation_settings"
CHECKS = {
    "ck_interview_automation_first": "first_reminder_hours IS NULL OR first_reminder_hours BETWEEN 1 AND 168",
    "ck_interview_automation_second": "second_reminder_hours IS NULL OR second_reminder_hours BETWEEN 1 AND 168",
    "ck_interview_automation_order": "first_reminder_hours IS NULL OR second_reminder_hours IS NULL OR second_reminder_hours < first_reminder_hours",
    "ck_interview_automation_chase": "chase_after_hours IS NULL OR chase_after_hours BETWEEN 1 AND 720",
    "ck_interview_automation_escalate": "escalate_after_hours IS NULL OR escalate_after_hours BETWEEN 1 AND 720",
}
COLUMNS = ("first_reminder_at", "second_reminder_at", "chase_follow_up_id", "chase_escalated_at")
FK = "fk_interviews_chase_follow_up_id"


def _template_fk(name: str) -> sa.Column:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("recruiter_message_templates.id", ondelete="RESTRICT"), nullable=True)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    have = {c["name"] for c in inspector.get_columns("interviews")}
    for name in COLUMNS:
        if name in have:
            continue
        kind = sa.Uuid() if name == "chase_follow_up_id" else sa.DateTime(timezone=True)
        op.add_column("interviews", sa.Column(name, kind, nullable=True))
    if not any(fk["constrained_columns"] == ["chase_follow_up_id"] for fk in inspector.get_foreign_keys("interviews")):
        op.create_foreign_key(FK, "interviews", "recruiter_follow_ups", ["chase_follow_up_id"], ["id"], ondelete="RESTRICT")
    if not inspector.has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.SmallInteger(), primary_key=True),
            sa.Column("first_reminder_hours", sa.SmallInteger(), nullable=True, server_default=sa.text("24")),
            sa.Column("second_reminder_hours", sa.SmallInteger(), nullable=True, server_default=sa.text("2")),
            _template_fk("reminder_template_id"),
            sa.Column("chase_after_hours", sa.SmallInteger(), nullable=True, server_default=sa.text("24")),
            sa.Column("escalate_after_hours", sa.SmallInteger(), nullable=True, server_default=sa.text("24")),
            _template_fk("chase_template_id"),
            sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        )
    op.execute(f"INSERT INTO {TABLE} (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
    # A7: no backlog -- what already started or starts within a day is not reminded; what already started is not chased
    op.execute("UPDATE interviews SET first_reminder_at = now() WHERE first_reminder_at IS NULL AND scheduled_at <= now() + interval '24 hours'")
    op.execute("UPDATE interviews SET second_reminder_at = now() WHERE second_reminder_at IS NULL AND scheduled_at <= now() + interval '24 hours'")
    op.execute("UPDATE interviews SET chase_escalated_at = now() WHERE chase_escalated_at IS NULL AND chase_follow_up_id IS NULL AND scheduled_at <= now()")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(TABLE):
        op.drop_table(TABLE)
    have = {c["name"] for c in inspector.get_columns("interviews")}
    for name in COLUMNS:
        if name in have:
            op.drop_column("interviews", name)  # Postgres drops the chase follow-up's foreign key with its column
