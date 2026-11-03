"""itc-022 -- programme modules/topics, topic completions, the computed-progress formula, remediation plans, the progress override reason.

Revision ID: 0247_it_training_progress
Revises: 0246_fee_adjustments

docs/superpowers/specs/2026-11-03-itc-022-modules-progress-remediation-design.md (DEC-SCOPE-365). Five new tables and one nullable column;
no existing row changes and no data moves (P1: the IT Admin copies the syllabus into a plan). 0001 builds a fresh database from the
current models, which already carry them, so each is created only when missing (0222's idiom). STATUSES is a frozen copy of the model's
tuple at this revision. The downgrade drops the tables and the column.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0247_it_training_progress"
down_revision = "0246_fee_adjustments"
branch_labels = None
depends_on = None

STATUSES = ("open", "in_progress", "completed", "cancelled")
TABLES = ("remediation_plans", "topic_completions", "program_topics", "program_modules", "it_progress_formulas")  # drop order


def upgrade() -> None:
    offline = op.get_context().as_sql
    bind = None if offline else op.get_bind()
    tables = set() if offline else set(sa.inspect(bind).get_table_names())
    columns = set() if offline else {c["name"] for c in sa.inspect(bind).get_columns("enrollments")}
    uuid = postgresql.UUID(as_uuid=True)
    created = (sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),)

    def stamps():
        return (*(c.copy() for c in created), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

    if "progress_override_reason" not in columns:
        op.add_column("enrollments", sa.Column("progress_override_reason", sa.String(500), nullable=True))
    if "it_progress_formulas" not in tables:
        op.create_table(
            "it_progress_formulas",
            sa.Column("program_id", uuid, sa.ForeignKey("programs.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("topics_weight", sa.Integer, nullable=False),
            sa.Column("assignments_weight", sa.Integer, nullable=False),
            sa.Column("assessments_weight", sa.Integer, nullable=False),
            sa.Column("updated_by_id", uuid, sa.ForeignKey("users.id"), nullable=True),
            *stamps(),
            sa.CheckConstraint(
                "topics_weight BETWEEN 0 AND 100 AND assignments_weight BETWEEN 0 AND 100 AND assessments_weight BETWEEN 0 AND 100",
                name="ck_it_progress_formulas_range",
            ),
            sa.CheckConstraint("topics_weight + assignments_weight + assessments_weight = 100", name="ck_it_progress_formulas_sum"),
        )
    if "program_modules" not in tables:
        op.create_table(
            "program_modules",
            sa.Column("id", uuid, primary_key=True),
            sa.Column("program_id", uuid, sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("position", sa.Integer, nullable=False),
            *stamps(),
        )
        op.create_index("ix_program_modules_program_position", "program_modules", ["program_id", "position"])
    if "program_topics" not in tables:
        op.create_table(
            "program_topics",
            sa.Column("id", uuid, primary_key=True),
            sa.Column("module_id", uuid, sa.ForeignKey("program_modules.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("position", sa.Integer, nullable=False),
            *stamps(),
        )
        op.create_index("ix_program_topics_module_position", "program_topics", ["module_id", "position"])
    if "topic_completions" not in tables:
        op.create_table(
            "topic_completions",
            sa.Column("id", uuid, primary_key=True),
            sa.Column("topic_id", uuid, sa.ForeignKey("program_topics.id", ondelete="CASCADE"), nullable=False),
            sa.Column("enrollment_id", uuid, sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
            sa.Column("completed_by_id", uuid, sa.ForeignKey("users.id"), nullable=False),
            *(c.copy() for c in created),
            sa.UniqueConstraint("topic_id", "enrollment_id", name="uq_topic_completions_topic_enrollment"),
        )
        op.create_index("ix_topic_completions_enrollment_id", "topic_completions", ["enrollment_id"])
    if "remediation_plans" not in tables:
        op.create_table(
            "remediation_plans",
            sa.Column("id", uuid, primary_key=True),
            sa.Column("enrollment_id", uuid, sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
            sa.Column("student_id", uuid, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("risk_flag_id", uuid, sa.ForeignKey("student_risk_flags.id", ondelete="SET NULL"), nullable=True),
            sa.Column("actions", sa.Text, nullable=False),
            sa.Column("owner_user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("due_date", sa.Date, nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="open"),
            sa.Column("created_by_id", uuid, sa.ForeignKey("users.id"), nullable=False),
            *stamps(),
            sa.CheckConstraint("status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")", name="ck_remediation_plans_status"),
        )
        op.create_index("ix_remediation_plans_student_id", "remediation_plans", ["student_id"])
        op.create_index("ix_remediation_plans_enrollment_id", "remediation_plans", ["enrollment_id"])


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("ALTER TABLE enrollments DROP COLUMN IF EXISTS progress_override_reason")
