"""pob-027 -- intake automation: the task template, requirement tasks and escalation rules (DEC-SCOPE-434 I3-I8, I11).

Revision ID: 0317_intake_automation
Revises: 0316_placement_surveys

docs/superpowers/specs/2026-11-08-pob-027-intake-automation-design.md. Additive only: four new tables and the settings row with the
default template. 0001 runs `create_all` from today's models, so a fresh database already has the tables: each is created only when
missing, and the row is inserted only when missing. TASK_CHECKS and RULE_CHECKS are frozen copies of `models.REQUIREMENT_TASK_CHECKS`
and `models.ESCALATION_RULE_CHECKS`. The downgrade drops the four tables.
"""

import json

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0317_intake_automation"
down_revision = "0316_placement_surveys"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TASK_CHECKS = {
    "ck_requirement_tasks_kind": "kind IN ('sourcing', 'screening')",
    "ck_requirement_tasks_status": "status IN ('open', 'done', 'cancelled')",
    "ck_requirement_tasks_done": "(status = 'done') = (completed_at IS NOT NULL) AND (completed_at IS NULL) = (completed_by_user_id IS NULL)",
}
RULE_CHECKS = {
    "ck_escalation_rules_event_type": "event_type IN ('requirement_unowned', 'requirement_task_overdue', 'follow_up_overdue')",
    "ck_escalation_rules_notify": "notify IN ('reporting_manager', 'all_team_leads')",
    "ck_escalation_rules_hours": "after_hours BETWEEN 1 AND 720",
}
DEFAULT_TEMPLATE = [
    {"kind": "sourcing", "title": "Prepare the sourcing plan", "due_in_hours": 24},
    {"kind": "screening", "title": "Screen the first shortlisted profiles", "due_in_hours": 72},
]


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    offline = op.get_context().as_sql
    tables = set() if offline else set(sa.inspect(op.get_bind()).get_table_names())
    if "requirement_automation_settings" not in tables:
        op.create_table(
            "requirement_automation_settings",
            sa.Column("id", sa.SmallInteger(), primary_key=True),
            sa.Column("task_template", sa.JSON(), nullable=False),
            sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            *_timestamps(),
        )
    if "requirement_tasks" not in tables:
        op.create_table(
            "requirement_tasks",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("assignee_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("status", sa.String(16), server_default=sa.text("'open'"), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            *_timestamps(),
            *(sa.CheckConstraint(sql, name=name) for name, sql in TASK_CHECKS.items()),
        )
        op.create_index("ix_requirement_tasks_job", "requirement_tasks", ["job_id", "status", "due_at"])
        op.create_index("ix_requirement_tasks_open_due", "requirement_tasks", ["due_at"], postgresql_where=sa.text("status = 'open'"))
    if "escalation_rules" not in tables:
        op.create_table(
            "escalation_rules",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("event_type", sa.String(40), nullable=False),
            sa.Column("after_hours", sa.SmallInteger(), nullable=False),
            sa.Column("notify", sa.String(24), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            *_timestamps(),
            *(sa.CheckConstraint(sql, name=name) for name, sql in RULE_CHECKS.items()),
        )
    if "escalation_events" not in tables:
        op.create_table(
            "escalation_events",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("rule_id", UUID, sa.ForeignKey("escalation_rules.id", ondelete="CASCADE"), nullable=False),
            sa.Column("entity_id", UUID, nullable=False),
            sa.Column("fired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("rule_id", "entity_id", name="uq_escalation_events_rule_entity"),
        )
    template = json.dumps(DEFAULT_TEMPLATE).replace("'", "''")
    op.execute(f"INSERT INTO requirement_automation_settings (id, task_template) VALUES (1, '{template}') ON CONFLICT (id) DO NOTHING")


def downgrade() -> None:
    op.drop_table("escalation_events")
    op.drop_table("escalation_rules")
    op.drop_table("requirement_tasks")
    op.drop_table("requirement_automation_settings")
