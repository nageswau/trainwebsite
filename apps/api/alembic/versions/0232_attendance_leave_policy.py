"""itc-021 -- attendance: who marked it, the day's live session, and the approved-leave % policy.

Revision ID: 0232_attendance_leave_policy
Revises: 0231_trainer_profiles

DEC-SCOPE-349. `attendance` gains `marked_by_id` (users) and `session_id` (live_sessions, ON DELETE SET NULL), both nullable: rows
marked before this revision keep NULL ("not recorded") rather than a guessed marker or session. `certificate_rules` gains
`leave_policy` (attended | excluded | absent), NOT NULL DEFAULT 'attended' -- today's rule, so no attendance % changes on upgrade.
The status values are unchanged ("excused" is labelled "Approved leave"), so no CHECK is added to `attendance.status`.
0001 builds a fresh database from the current models, so every column/constraint is added only when missing. Downgrade drops them.
"""

from alembic import op

revision = "0232_attendance_leave_policy"
down_revision = "0231_trainer_profiles"
branch_labels = None
depends_on = None

POLICIES = ("attended", "excluded", "absent")  # frozen copy of models.LEAVE_POLICIES


def upgrade() -> None:
    op.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS marked_by_id UUID REFERENCES users(id)")
    op.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES live_sessions(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_attendance_session_id ON attendance (session_id)")
    op.execute("ALTER TABLE certificate_rules ADD COLUMN IF NOT EXISTS leave_policy VARCHAR(20) NOT NULL DEFAULT 'attended'")
    op.execute("ALTER TABLE certificate_rules DROP CONSTRAINT IF EXISTS ck_certificate_rules_leave_policy")
    op.execute(f"ALTER TABLE certificate_rules ADD CONSTRAINT ck_certificate_rules_leave_policy CHECK (leave_policy IN ({', '.join(repr(p) for p in POLICIES)}))")


def downgrade() -> None:
    op.execute("ALTER TABLE certificate_rules DROP CONSTRAINT IF EXISTS ck_certificate_rules_leave_policy")
    op.execute("ALTER TABLE certificate_rules DROP COLUMN IF EXISTS leave_policy")
    op.execute("DROP INDEX IF EXISTS ix_attendance_session_id")
    op.execute("ALTER TABLE attendance DROP COLUMN IF EXISTS session_id")
    op.execute("ALTER TABLE attendance DROP COLUMN IF EXISTS marked_by_id")
