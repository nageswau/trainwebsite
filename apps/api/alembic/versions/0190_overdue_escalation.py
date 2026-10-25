"""ccrm-031 -- the `overdue_escalation` reminder rule: widen the rule-key CHECK and seed the E1 default.

Revision ID: 0190_overdue_escalation
Revises: 0189_counselor_reminders

docs/superpowers/specs/2026-10-25-ccrm-031-overdue-escalation-design.md (DEC-SCOPE-271). 0001 builds a fresh database from the current
models, whose CHECK already carries the new key, so the constraint is dropped if it exists and re-created; the seed is ON CONFLICT DO
NOTHING. The downgrade removes the rule's row and log rows, then restores 0189's ten keys.
"""

from alembic import op

revision = "0190_overdue_escalation"
down_revision = "0189_counselor_reminders"
branch_labels = None
depends_on = None

OLD_KEYS = (
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
RULE_KEYS = (*OLD_KEYS, "overdue_escalation")
KEY_CHECK = "ck_counselor_reminder_rules_key"
DEFAULT = ("overdue_escalation", 2, False)  # E1: (offset_days, notify_student) -- frozen here


def _key_check(keys: tuple[str, ...]) -> str:
    return f"rule_key IN ({', '.join(repr(k) for k in keys)})"


def _replace_check(keys: tuple[str, ...]) -> None:
    op.execute(f"ALTER TABLE counselor_reminder_rules DROP CONSTRAINT IF EXISTS {KEY_CHECK}")
    op.create_check_constraint(KEY_CHECK, "counselor_reminder_rules", _key_check(keys))


def upgrade() -> None:
    _replace_check(RULE_KEYS)
    key, offset, student = DEFAULT
    op.execute(f"INSERT INTO counselor_reminder_rules (rule_key, offset_days, notify_student) VALUES ('{key}', {offset}, {str(student).lower()}) ON CONFLICT (rule_key) DO NOTHING")


def downgrade() -> None:
    op.execute("DELETE FROM counselor_reminder_log WHERE rule_key = 'overdue_escalation'")
    op.execute("DELETE FROM counselor_reminder_rules WHERE rule_key = 'overdue_escalation'")
    _replace_check(OLD_KEYS)
