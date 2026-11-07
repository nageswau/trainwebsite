"""pob-008 -- recruiter follow-up reminders and outreach cadences: `recruiter_follow_ups.reminded_at` (+ its partial index), the
`first_outreach` / `cadence_step` reasons, `recruiter_cadences` and `recruiter_contact_cadences`.

Revision ID: 0304_outreach_cadences
Revises: 0303_company_bd_stages

docs/superpowers/specs/2026-11-07-pob-008-follow-up-reminders-cadences-design.md (DEC-SCOPE-423). 0001 builds a fresh database from the current
models, which already carry all of this, so each column, index and table is added only when missing (0302's idiom); the checks are dropped and
re-created from frozen copies. B12: open follow-ups already past due are stamped `reminded_at = now()`, so the first sweep sends no backlog. The
downgrade deletes no follow-up: the two new reasons become `new_openings` so the old check holds.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0304_outreach_cadences"
down_revision = "0303_company_bd_stages"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
OLD_REASONS = (
    "'new_requirement', 'jd', 'profile_feedback', 'interview_feedback', 'offer_status', 'joining_confirmation', 'new_openings', "
    "'contract_mou', 'payment_commercial', 'clarification'"
)
REASON = "ck_recruiter_follow_ups_reason"
REASON_CHECK = f"reason IN ({OLD_REASONS}, 'first_outreach', 'cadence_step')"  # frozen copy (test_pob_008_migration)
OLD_REASON_CHECK = f"reason IN ({OLD_REASONS})"
RUN_CHECKS = {  # frozen copies of RECRUITER_CONTACT_CADENCE_CHECKS at this revision
    "ck_recruiter_contact_cadences_status": "status IN ('active', 'replied', 'stopped', 'completed')",
    "ck_recruiter_contact_cadences_end_reason": (
        "end_reason IS NULL OR end_reason IN ('reply', 'do_not_contact', 'not_interested', 'inactive', 'archived', 'manual', 'last_step')"
    ),
    "ck_recruiter_contact_cadences_state": (
        "(status = 'active') = (ended_at IS NULL) AND (ended_at IS NULL) = (end_reason IS NULL) AND (status = 'active') = (next_step_at IS NOT NULL)"
    ),
}
CADENCES, RUNS, FOLLOW_UPS = "recruiter_cadences", "recruiter_contact_cadences", "recruiter_follow_ups"
UNREMINDED = "ix_recruiter_follow_ups_unreminded"


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))  # fmt: skip


def _set_reason(sql: str) -> None:
    op.execute(f"ALTER TABLE {FOLLOW_UPS} DROP CONSTRAINT IF EXISTS {REASON}")
    op.create_check_constraint(REASON, FOLLOW_UPS, sql)


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    tables = set() if offline else set(inspector.get_table_names())
    if offline or "reminded_at" not in {c["name"] for c in inspector.get_columns(FOLLOW_UPS)}:
        op.add_column(FOLLOW_UPS, sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(f"CREATE INDEX IF NOT EXISTS {UNREMINDED} ON {FOLLOW_UPS} (due_at) WHERE status = 'open' AND reminded_at IS NULL")
    _set_reason(REASON_CHECK)
    if CADENCES not in tables:
        op.create_table(
            CADENCES,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.String(500), nullable=True),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("steps", sa.JSON(), nullable=False),
            sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            *_timestamps(),
        )
        op.create_index("uq_recruiter_cadences_name", CADENCES, [sa.text("lower(name)")], unique=True)
    if RUNS not in tables:
        op.create_table(
            RUNS,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("cadence_id", UUID, sa.ForeignKey("recruiter_cadences.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("contact_id", UUID, sa.ForeignKey("company_contacts.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("message_id", UUID, sa.ForeignKey("recruiter_messages.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("steps", sa.JSON(), nullable=False),
            sa.Column("step", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
            sa.Column("status", sa.String(12), server_default=sa.text("'active'"), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("next_step_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("end_reason", sa.String(20), nullable=True),
            sa.Column("last_follow_up_id", UUID, sa.ForeignKey("recruiter_follow_ups.id", ondelete="RESTRICT"), nullable=True),
            *_timestamps(),
            *(sa.CheckConstraint(sql, name=name) for name, sql in RUN_CHECKS.items()),
        )
        op.create_index("uq_recruiter_contact_cadences_active", RUNS, ["contact_id"], unique=True, postgresql_where=sa.text("status = 'active'"))
        op.create_index("ix_recruiter_contact_cadences_due", RUNS, ["next_step_at"], postgresql_where=sa.text("status = 'active'"))
        op.create_index("ix_recruiter_contact_cadences_message", RUNS, ["message_id"])
    op.execute(f"UPDATE {FOLLOW_UPS} SET reminded_at = now() WHERE status = 'open' AND reminded_at IS NULL AND due_at < now()")  # B12


def downgrade() -> None:
    op.drop_table(RUNS)
    op.drop_table(CADENCES)
    op.execute(f"UPDATE {FOLLOW_UPS} SET reason = 'new_openings' WHERE reason IN ('first_outreach', 'cadence_step')")
    _set_reason(OLD_REASON_CHECK)
    op.execute(f"DROP INDEX IF EXISTS {UNREMINDED}")
    op.drop_column(FOLLOW_UPS, "reminded_at")
