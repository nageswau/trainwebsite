"""bdm-016 -- bdm_targets.

Revision ID: 0095_bdm_targets
Revises: 0094_bdm_daily_reports

docs/superpowers/specs/2026-10-07-bdm-016-monthly-targets-design.md §4 (DEC-SCOPE-100). Additive: one table; no existing row is read or
written. 0001 builds a fresh database from the current models, which already carry it, so creation is guarded (0071's idiom).
downgrade() refuses while targets exist: each is the only record of what a manager set for that month.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0095_bdm_targets"
down_revision = "0094_bdm_daily_reports"
branch_labels = None
depends_on = None

TABLE = "bdm_targets"
# Frozen copies of the model's rules; test_bdm_016_migration asserts they stay identical.
CHECKS = {
    "ck_bdm_targets_month_start": "EXTRACT(DAY FROM month) = 1",
    "ck_bdm_targets_target_range": "target >= 0 AND target <= 100000",
}


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("bdm_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("kpi_key", sa.String(40), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.Column("set_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("bdm_user_id", "month", "kpi_key", name="uq_bdm_targets_bdm_month_kpi"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0095_bdm_targets: BDM targets exist. Remove them deliberately first.")
    op.drop_table(TABLE)
