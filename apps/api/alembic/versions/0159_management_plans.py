"""mgmt-026 -- the next month plan: management_plans + management_plan_items.

Revision ID: 0159_management_plans
Revises: 0158_social_proof

docs/superpowers/specs/2026-10-14-mgmt-026-next-month-plan-design.md §5 (DEC-SCOPE-211). New tables only; no existing row changes.
0001 builds a fresh database from the current models, which already carry these tables, so they are created only when missing (0122's
idiom). downgrade() refuses while any plan exists: management plans are never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0159_management_plans"
down_revision = "0158_social_proof"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
# Frozen copies of app.models.PLAN_STATUSES / PLAN_VERTICALS / PLAN_ITEM_CHECKS.
STATUSES = ("draft", "active", "closed")
VERTICALS = ("abroad", "it", "school", "recruitment", "other")
ITEM_CHECKS = {
    "ck_management_plan_items_vertical": "vertical IN ('abroad', 'it', 'school', 'recruitment', 'other')",
    "ck_management_plan_items_kpi_target": "(kpi IS NULL) = (target IS NULL)",
    "ck_management_plan_items_target": "target IS NULL OR target > 0",
    "ck_management_plan_items_done": "kpi IS NULL OR NOT done",
}


def _user(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


def _stamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    existing = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())
    if "management_plans" not in existing:
        op.create_table(
            "management_plans",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("month", sa.Date(), nullable=False),
            sa.Column("status", sa.String(8), server_default=sa.text("'draft'"), nullable=False),
            _user("created_by_user_id"),
            _user("updated_by_user_id"),
            *_stamps(),
            sa.UniqueConstraint("month", name="uq_management_plans_month"),
            sa.CheckConstraint("EXTRACT(DAY FROM month) = 1", name="ck_management_plans_month"),
            sa.CheckConstraint(f"status IN ({', '.join(repr(s) for s in STATUSES)})", name="ck_management_plans_status"),
        )
    if "management_plan_items" not in existing:
        op.create_table(
            "management_plan_items",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("plan_id", UUID, sa.ForeignKey("management_plans.id", ondelete="CASCADE"), nullable=False),
            sa.Column("vertical", sa.String(12), nullable=False),
            sa.Column("text", sa.String(200), nullable=False),
            sa.Column("kpi", sa.String(20), nullable=True),
            sa.Column("target", sa.Numeric(16, 2), nullable=True),
            sa.Column("done", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            _user("created_by_user_id"),
            _user("updated_by_user_id"),
            *_stamps(),
            *(sa.CheckConstraint(sql, name=name) for name, sql in ITEM_CHECKS.items()),
        )
        op.create_index("ix_management_plan_items_plan_order", "management_plan_items", ["plan_id", "vertical", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM management_plans LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0159_management_plans: plans exist. Clear them deliberately first.")
    op.drop_table("management_plan_items")
    op.drop_table("management_plans")
