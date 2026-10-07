"""bdm-015 -- bdm_daily_reports.

Revision ID: 0092_bdm_daily_reports
Revises: 0091_lead_appointments

docs/superpowers/specs/2026-10-07-bdm-015-daily-activity-report-design.md §4 (DEC-SCOPE-096). Additive: one table; no existing row is
read or written. 0001 builds a fresh database from the current models, which already carry it, so creation is guarded (0071's idiom).
downgrade() refuses while reports exist: each is the only record of what a BDM submitted for that day.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0092_bdm_daily_reports"
down_revision = "0091_lead_appointments"
branch_labels = None
depends_on = None

TABLE = "bdm_daily_reports"
# Frozen copies of the model's rules; test_bdm_015_migration asserts they stay identical.
CHECKS = {
    "ck_bdm_daily_reports_bdm_type": "bdm_type IN ('agent', 'school', 'college')",
    "ck_bdm_daily_reports_comment": "(manager_comment IS NULL) = (manager_comment_by_user_id IS NULL) AND (manager_comment IS NULL) = (manager_commented_at IS NULL)",
}


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("bdm_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("bdm_type", sa.String(20), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(2000), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("manager_comment", sa.String(1000), nullable=True),
        sa.Column("manager_comment_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("manager_commented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("bdm_user_id", "report_date", name="uq_bdm_daily_reports_bdm_date"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0092_bdm_daily_reports: BDM daily reports exist. Remove them deliberately first.")
    op.drop_table(TABLE)
