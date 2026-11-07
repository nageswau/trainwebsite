"""pob-009 -- PO targets, target companies, the daily plan, activity reports and territories.

Revision ID: 0304_po_targets_reports
Revises: 0303_company_bd_stages

docs/superpowers/specs/2026-11-07-pob-009-po-targets-reports-design.md. 0001 builds a fresh database from today's models, so every object
is created only when missing. Additive only: no existing row changes. downgrade() drops the four tables and the two territory columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0304_po_targets_reports"
down_revision = "0303_company_bd_stages"
branch_labels = None
depends_on = None

# Frozen copies of app.models.* at this revision (test_pob_009_migration checks parity).
KPIS = ("outreach", "responses", "meetings", "requirements", "vendor_registrations", "active_accounts", "placements")
TARGET_CHECKS = {
    "ck_recruiter_targets_month_start": "EXTRACT(DAY FROM month) = 1",
    "ck_recruiter_targets_target_range": "target >= 0 AND target <= 100000",
    "ck_recruiter_targets_kpi": "kpi_key IN (" + ", ".join(f"'{k}'" for k in KPIS) + ")",
}
TARGET_COMPANY_CHECKS = {"ck_recruiter_target_companies_month_start": "EXTRACT(DAY FROM month) = 1"}
PLAN_ITEM_CHECKS = {"ck_recruiter_plan_items_one_subject": "(follow_up_id IS NULL) <> (company_id IS NULL)"}
REPORT_CHECKS = {
    "ck_recruiter_activity_reports_period": "period IN ('daily', 'weekly')",
    "ck_recruiter_activity_reports_monday": "period = 'daily' OR EXTRACT(ISODOW FROM period_start) = 1",
}
TERRITORY = (("companies", "territory"), ("recruiter_profiles", "territory"))
TABLES = ("recruiter_activity_reports", "recruiter_plan_items", "recruiter_target_companies", "recruiter_targets")


def _user(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def _checks(checks: dict) -> list:
    return [sa.CheckConstraint(sql, name=name) for name, sql in checks.items()]


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, column in TERRITORY:
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column(column, sa.String(120), nullable=True))
    if not inspector.has_table("recruiter_targets"):
        op.create_table(
            "recruiter_targets",
            sa.Column("id", sa.Uuid(), primary_key=True),
            _user("recruiter_user_id"),
            sa.Column("month", sa.Date(), nullable=False),
            sa.Column("kpi_key", sa.String(40), nullable=False),
            sa.Column("target", sa.Integer(), nullable=False),
            _user("set_by_user_id"),
            sa.Column("set_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("recruiter_user_id", "month", "kpi_key", name="uq_recruiter_targets_user_month_kpi"),
            *_checks(TARGET_CHECKS),
        )
    if not inspector.has_table("recruiter_target_companies"):
        op.create_table(
            "recruiter_target_companies",
            sa.Column("id", sa.Uuid(), primary_key=True),
            _user("recruiter_user_id"),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("month", sa.Date(), nullable=False),
            _user("added_by_user_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("recruiter_user_id", "month", "company_id", name="uq_recruiter_target_companies"),
            *_checks(TARGET_COMPANY_CHECKS),
        )
        op.create_index("ix_recruiter_target_companies_company", "recruiter_target_companies", ["company_id"])
    if not inspector.has_table("recruiter_plan_items"):
        op.create_table(
            "recruiter_plan_items",
            sa.Column("id", sa.Uuid(), primary_key=True),
            _user("recruiter_user_id"),
            sa.Column("plan_date", sa.Date(), nullable=False),
            sa.Column("follow_up_id", sa.Uuid(), sa.ForeignKey("recruiter_follow_ups.id", ondelete="CASCADE"), nullable=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True),
            sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *_checks(PLAN_ITEM_CHECKS),
        )
        op.create_index("uq_recruiter_plan_items_follow_up", "recruiter_plan_items", ["recruiter_user_id", "plan_date", "follow_up_id"], unique=True,
                        postgresql_where=sa.text("follow_up_id IS NOT NULL"))
        op.create_index("uq_recruiter_plan_items_company", "recruiter_plan_items", ["recruiter_user_id", "plan_date", "company_id"], unique=True,
                        postgresql_where=sa.text("company_id IS NOT NULL"))
    if not inspector.has_table("recruiter_activity_reports"):
        op.create_table(
            "recruiter_activity_reports",
            sa.Column("id", sa.Uuid(), primary_key=True),
            _user("recruiter_user_id"),
            sa.Column("period", sa.String(10), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("counts", sa.JSON(), nullable=False),
            sa.Column("note", sa.String(2000), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("recruiter_user_id", "period", "period_start", name="uq_recruiter_activity_reports"),
            *_checks(REPORT_CHECKS),
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")
    for table, column in TERRITORY:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
