"""ccrm-030 -- counselor reminder rules (seeded with the RM1 defaults) and the reminder log with its unique dedupe key.

Revision ID: 0189_counselor_reminders
Revises: 0188_student_document_requests

docs/superpowers/specs/2026-10-25-ccrm-030-counselor-reminders-design.md (DEC-SCOPE-270). 0001 builds a fresh database from the current
models, which already carry both tables, so each table is created only when missing (0166's idiom); the seed is ON CONFLICT DO NOTHING
either way. The downgrade drops both tables (the log and the admin's settings go; rule tasks stay as ordinary tasks).
"""

import sqlalchemy as sa

from alembic import op

revision = "0189_counselor_reminders"
down_revision = "0188_student_document_requests"
branch_labels = None
depends_on = None

RULE_KEYS = (
    "first_contact",
    "no_response",
    "document_overdue",
    "application_deadline",
    "decision_overdue",
    "offer_deadline",
    "deposit_due",
    "condition_due",
    "visa_appointment",
    "hold_review",
)
MAX_OFFSET = 60
CHECKS = {
    "ck_counselor_reminder_rules_key": f"rule_key IN ({', '.join(repr(k) for k in RULE_KEYS)})",
    "ck_counselor_reminder_rules_offset": f"offset_days BETWEEN 0 AND {MAX_OFFSET}",
}
# RM1: (offset_days, notify_student) -- frozen here; services/counselor_reminders.RULES is the live catalogue
DEFAULTS = {
    "first_contact": (1, False),
    "no_response": (3, False),
    "document_overdue": (0, True),
    "application_deadline": (7, False),
    "decision_overdue": (0, False),
    "offer_deadline": (3, True),
    "deposit_due": (3, True),
    "condition_due": (3, True),
    "visa_appointment": (2, False),
    "hold_review": (0, False),
}


def _has_table(name: str) -> bool:
    return not op.get_context().as_sql and sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("counselor_reminder_rules"):
        op.create_table(
            "counselor_reminder_rules",
            sa.Column("rule_key", sa.String(40), primary_key=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("offset_days", sa.Integer(), nullable=False),
            sa.Column("notify_student", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        )
    if not _has_table("counselor_reminder_log"):
        op.create_table(
            "counselor_reminder_log",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("rule_key", sa.String(40), nullable=False),
            sa.Column("dedupe_key", sa.String(200), nullable=False),
            sa.Column("subject_id", sa.Uuid(), nullable=False),
            sa.Column("summary", sa.String(200), nullable=False),
            sa.Column("task_id", sa.Uuid(), sa.ForeignKey("counselor_tasks.id", ondelete="SET NULL"), nullable=True),
            sa.Column("recipients", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("dedupe_key", name="uq_counselor_reminder_log_dedupe_key"),
        )
        op.create_index("ix_counselor_reminder_log_created", "counselor_reminder_log", ["created_at"])
    values = ", ".join(f"('{key}', {offset}, {str(student).lower()})" for key, (offset, student) in DEFAULTS.items())
    op.execute(f"INSERT INTO counselor_reminder_rules (rule_key, offset_days, notify_student) VALUES {values} ON CONFLICT (rule_key) DO NOTHING")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS counselor_reminder_log")
    op.execute("DROP TABLE IF EXISTS counselor_reminder_rules")
