"""itc-023 -- at-risk thresholds per programme and the student risk flags (with history).

Revision ID: 0236_it_at_risk
Revises: 0235_student_resumes

DEC-SCOPE-352. Two new tables, nothing existing is altered: `it_risk_thresholds` (one row per programme; no row = not monitored, so
nothing is flagged on upgrade) and `student_risk_flags` (one row per at-risk episode; the partial unique index allows one open flag per
enrolment). 0001 builds a fresh database from the current models, so every object is created only when missing. Downgrade drops both.
"""

from alembic import op

revision = "0236_it_at_risk"
down_revision = "0235_student_resumes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS it_risk_thresholds (
            program_id UUID PRIMARY KEY REFERENCES programs(id) ON DELETE CASCADE,
            min_attendance_percent INTEGER,
            min_assessment_percent INTEGER,
            max_consecutive_absences INTEGER,
            min_sessions INTEGER NOT NULL DEFAULT 3,
            updated_by_id UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_it_risk_thresholds_percent CHECK (min_attendance_percent BETWEEN 0 AND 100 AND min_assessment_percent BETWEEN 0 AND 100),
            CONSTRAINT ck_it_risk_thresholds_counts CHECK (max_consecutive_absences BETWEEN 1 AND 60 AND min_sessions BETWEEN 1 AND 60)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS student_risk_flags (
            id UUID PRIMARY KEY,
            enrollment_id UUID NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
            student_id UUID NOT NULL REFERENCES users(id),
            batch_id UUID NOT NULL REFERENCES batches(id),
            reasons JSON NOT NULL,
            attendance_percent NUMERIC(5, 2),
            assessment_percent NUMERIC(5, 2),
            consecutive_absences INTEGER NOT NULL DEFAULT 0,
            raised_at TIMESTAMPTZ NOT NULL,
            cleared_at TIMESTAMPTZ,
            clear_reason VARCHAR(20),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_student_risk_flags_clear_reason CHECK (clear_reason IS NULL OR clear_reason IN ('recovered', 'stopped'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_student_risk_flags_enrollment_id ON student_risk_flags (enrollment_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_student_risk_flags_student_id ON student_risk_flags (student_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_student_risk_flags_batch_id ON student_risk_flags (batch_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_student_risk_flags_open ON student_risk_flags (enrollment_id) WHERE cleared_at IS NULL")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS student_risk_flags")
    op.execute("DROP TABLE IF EXISTS it_risk_thresholds")
