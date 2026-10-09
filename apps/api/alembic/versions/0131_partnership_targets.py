"""upc-021 -- partnership_targets.

Revision ID: 0131_partnership_targets
Revises: 0130_university_meetings

docs/superpowers/specs/2026-10-09-upc-021-partnership-targets-design.md §3 (DEC-SCOPE-146). Additive: one table; no existing row is read
or written. 0001 builds a fresh database from the current models, which already carry it, so creation is guarded (0096's idiom). CHECKS
repeats app.models (test_upc_021_migration). downgrade() refuses while targets exist: each is the only record of what a head set.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0131_partnership_targets"
down_revision = "0130_university_meetings"
branch_labels = None
depends_on = None

TABLE = "partnership_targets"
KPIS = ("new_universities", "contacted", "meetings", "proposals", "negotiations", "mous", "new_active")
CHECKS = {
    "ck_partnership_targets_month_start": "EXTRACT(DAY FROM month) = 1",
    "ck_partnership_targets_kpi": f"kpi_key IN ({', '.join(repr(k) for k in KPIS)})",
    "ck_partnership_targets_target_range": "target >= 0 AND target <= 100000",
}


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("manager_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("kpi_key", sa.String(40), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.Column("set_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("set_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("manager_user_id", "month", "kpi_key", name="uq_partnership_targets_manager_month_kpi"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0131_partnership_targets: partnership targets exist. Remove them deliberately first.")
    op.drop_table(TABLE)
