"""nehn-037 part 4 -- `application_interviews`: admission interviews on an overseas application.

Revision ID: 0203_application_interviews
Revises: 0202_learning_resource_files

docs/superpowers/specs/2026-10-27-nehn-037-admission-interviews-design.md (DEC-SCOPE-296). A new table only; no existing row changes.
MODES/OUTCOMES are frozen copies of the model constants at this revision (test_nehn_037_migration). The downgrade drops the table.
"""

import sqlalchemy as sa

from alembic import op

revision = "0203_application_interviews"
down_revision = "0202_learning_resource_files"
branch_labels = None
depends_on = None

MODES = ("online", "in_person", "phone")
OUTCOMES = ("passed", "not_successful", "cancelled")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(repr(v) for v in values)


def upgrade() -> None:
    # 0001 builds a fresh database from the current models, which already carry the table, so it is created only when missing (0200's idiom).
    offline = op.get_context().as_sql
    if not offline and "application_interviews" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "application_interviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("overseas_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("location", sa.String(300), nullable=True),
        sa.Column("student_note", sa.String(500), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"mode IN ({_quoted(MODES)})", name="ck_application_interviews_mode"),
        sa.CheckConstraint(f"outcome IS NULL OR outcome IN ({_quoted(OUTCOMES)})", name="ck_application_interviews_outcome"),
    )
    op.create_index("ix_application_interviews_application", "application_interviews", ["application_id", "scheduled_at"])


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS application_interviews")
