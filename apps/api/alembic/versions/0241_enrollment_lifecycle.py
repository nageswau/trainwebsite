"""itc-031 -- the unified IT student lifecycle: history table, override columns and the enrolment status CHECK.

Revision ID: 0241_enrollment_lifecycle
Revises: 0240_fee_reminders

DEC-SCOPE-359 L4/L6/L9. `enrollment_lifecycle_history` holds the transitions `services/it_lifecycle.py` writes (the stage itself is never
stored). `enrollments.lifecycle_override` (+ reason) holds the IT Admin's "not_placed"/"closed". `ck_enrollments_status` turns the free-text
status into the six values in use: it is added NOT VALID and validated only when no row breaks it, so existing data is never rewritten and
an unexpected legacy value still upgrades (new writes are checked either way). 0001 builds a fresh database from the current models, so
every object is created only when missing. Downgrade drops exactly what this adds.
"""

from alembic import op

revision = "0241_enrollment_lifecycle"
down_revision = "0240_fee_reminders"
branch_labels = None
depends_on = None

STATUSES = ("pending_consent", "active", "rejected", "withdrawn", "dropped", "completed")  # = models.ENROLLMENT_STATUSES (tested)
_IN = ", ".join(f"'{s}'" for s in STATUSES)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS enrollment_lifecycle_history (
            id UUID PRIMARY KEY,
            enrollment_id UUID NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
            from_stage VARCHAR(20),
            to_stage VARCHAR(20) NOT NULL,
            cause VARCHAR(20) NOT NULL,
            actor_user_id UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_enrollment_lifecycle_history_enrollment ON enrollment_lifecycle_history (enrollment_id, created_at)")
    op.execute("ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS lifecycle_override VARCHAR(20)")
    op.execute("ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS lifecycle_override_reason VARCHAR(500)")
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_enrollments_lifecycle_override') THEN
                ALTER TABLE enrollments ADD CONSTRAINT ck_enrollments_lifecycle_override
                    CHECK (lifecycle_override IS NULL OR lifecycle_override IN ('not_placed', 'closed'));
            END IF;
        END $$
        """
    )
    op.execute(
        f"""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_enrollments_status') THEN
                ALTER TABLE enrollments ADD CONSTRAINT ck_enrollments_status CHECK (status IN ({_IN})) NOT VALID;
                IF NOT EXISTS (SELECT 1 FROM enrollments WHERE status NOT IN ({_IN})) THEN
                    ALTER TABLE enrollments VALIDATE CONSTRAINT ck_enrollments_status;
                END IF;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE enrollments DROP CONSTRAINT IF EXISTS ck_enrollments_status")
    op.execute("ALTER TABLE enrollments DROP CONSTRAINT IF EXISTS ck_enrollments_lifecycle_override")
    op.execute("ALTER TABLE enrollments DROP COLUMN IF EXISTS lifecycle_override_reason")
    op.execute("ALTER TABLE enrollments DROP COLUMN IF EXISTS lifecycle_override")
    op.execute("DROP TABLE IF EXISTS enrollment_lifecycle_history")
