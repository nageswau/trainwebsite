"""itc-027 -- HR resume-review tasks, their stage history and the programme -> HR reviewer rules.

Revision ID: 0237_hr_review_tasks
Revises: 0236_it_at_risk

DEC-SCOPE-354. Three new tables, nothing existing is altered: `hr_review_tasks` (one per IT student, unique; the queue index on
`(owner_user_id, stage)`), `hr_review_stage_history` and `hr_assignment_rules` (one per programme). No task is created for resumes
uploaded before this revision -- the next shared upload creates it. 0001 builds a fresh database from the current models, so every
object is created only when missing. Downgrade drops all three.
"""

from alembic import op

revision = "0237_hr_review_tasks"
down_revision = "0236_it_at_risk"
branch_labels = None
depends_on = None

STAGES = ("resume_received", "under_review", "changes_requested", "screening", "interview_ready", "completed", "withdrawn")


def upgrade() -> None:
    stages = ", ".join(f"'{s}'" for s in STAGES)
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS hr_review_tasks (
            id UUID PRIMARY KEY,
            student_user_id UUID NOT NULL REFERENCES users(id),
            owner_user_id UUID REFERENCES users(id),
            stage VARCHAR(20) NOT NULL,
            resume_version INTEGER NOT NULL,
            screening_date DATE,
            role_preferences VARCHAR(300),
            skill_gap_notes TEXT,
            checklist JSON NOT NULL,
            assigned_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ,
            updated_by_user_id UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_hr_review_tasks_student UNIQUE (student_user_id),
            CONSTRAINT ck_hr_review_tasks_stage CHECK (stage IN ({stages}))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_hr_review_tasks_owner_stage ON hr_review_tasks (owner_user_id, stage)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_review_stage_history (
            id UUID PRIMARY KEY,
            task_id UUID NOT NULL REFERENCES hr_review_tasks(id) ON DELETE CASCADE,
            from_stage VARCHAR(20),
            to_stage VARCHAR(20) NOT NULL,
            actor_user_id UUID REFERENCES users(id),
            reason VARCHAR(20) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_hr_review_stage_history_task_id ON hr_review_stage_history (task_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_assignment_rules (
            program_id UUID PRIMARY KEY REFERENCES programs(id) ON DELETE CASCADE,
            hr_user_id UUID NOT NULL REFERENCES users(id),
            updated_by_user_id UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS hr_assignment_rules")
    op.execute("DROP TABLE IF EXISTS hr_review_stage_history")
    op.execute("DROP TABLE IF EXISTS hr_review_tasks")
