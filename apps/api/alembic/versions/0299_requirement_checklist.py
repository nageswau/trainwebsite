"""pob-016 -- the requirement validation checklist: `job_checklist_items`, `job_checklist_overrides`, `requirement_checklist_settings`,
`companies.checklist_blocks_sourcing` and the follow-up reason `clarification`.

Revision ID: 0299_requirement_checklist
Revises: 0298_template_governance

docs/superpowers/specs/2026-11-07-pob-016-requirement-checklist-design.md (DEC-SCOPE-419). 0001 builds a fresh database from the current models, which already
carry all of this, so each step runs only when missing (0256's idiom). The checks are frozen copies of the models at this revision. The upgrade changes no existing
row. The downgrade first turns `clarification` follow-ups into `jd` (the backlog's other named reason), so no follow-up is lost.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0299_requirement_checklist"
down_revision = "0298_template_governance"
branch_labels = None
depends_on = None

ITEM_CHECKS = {"ck_job_checklist_items_status": "status IN ('confirmed', 'not_applicable', 'missing')"}
OLD_REASONS = "'new_requirement', 'jd', 'profile_feedback', 'interview_feedback', 'offer_status', 'joining_confirmation', 'new_openings', 'contract_mou', 'payment_commercial'"
OLD_REASON_CHECK = f"reason IN ({OLD_REASONS})"
REASON_CHECK = f"reason IN ({OLD_REASONS}, 'clarification')"
REASON_NAME = "ck_recruiter_follow_ups_reason"
UUID = postgresql.UUID(as_uuid=True)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def _set_reason_check(sql: str) -> None:
    op.execute(f"ALTER TABLE recruiter_follow_ups DROP CONSTRAINT IF EXISTS {REASON_NAME}")
    op.create_check_constraint(REASON_NAME, "recruiter_follow_ups", sql)


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    _set_reason_check(REASON_CHECK)
    if offline or "checklist_blocks_sourcing" not in {c["name"] for c in inspector.get_columns("companies")}:
        op.add_column("companies", sa.Column("checklist_blocks_sourcing", sa.Boolean(), nullable=True))
    tables = set() if offline else set(inspector.get_table_names())
    if "job_checklist_items" not in tables:
        op.create_table(
            "job_checklist_items",
            sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("item_key", sa.String(40), primary_key=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("follow_up_id", UUID, sa.ForeignKey("recruiter_follow_ups.id", ondelete="SET NULL"), nullable=True),
            sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            *_timestamps(),
            *(sa.CheckConstraint(sql, name=name) for name, sql in ITEM_CHECKS.items()),
        )
    if "job_checklist_overrides" not in tables:
        op.create_table(
            "job_checklist_overrides",
            sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("overridden_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            *_timestamps(),
        )
    if "requirement_checklist_settings" not in tables:
        op.create_table(
            "requirement_checklist_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("block_sourcing", sa.Boolean(), nullable=False),
            sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            *_timestamps(),
        )


def downgrade() -> None:
    op.drop_table("requirement_checklist_settings")
    op.drop_table("job_checklist_overrides")
    op.drop_table("job_checklist_items")
    op.drop_column("companies", "checklist_blocks_sourcing")
    op.execute("UPDATE recruiter_follow_ups SET reason = 'jd' WHERE reason = 'clarification'")
    _set_reason_check(OLD_REASON_CHECK)
