"""mgmt-032 -- the Monthly Business Review: monthly_reviews.

Revision ID: 0163_monthly_reviews
Revises: 0162_school_values

docs/superpowers/specs/2026-10-14-mgmt-032-monthly-review-design.md (MR2, DEC-SCOPE-220). A new table only; no existing row changes.
0001 builds a fresh database from the current models, which already carry it, so it is created only when missing (0160's idiom).
downgrade() refuses while a final review exists: a finalised review's frozen figures cannot be regenerated (drafts can).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0163_monthly_reviews"
down_revision = "0162_school_values"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
CHECKS = {  # must equal app.models.REVIEW_CHECKS
    "ck_monthly_reviews_month": "EXTRACT(DAY FROM month) = 1",
    "ck_monthly_reviews_status": "status IN ('draft', 'final')",
    "ck_monthly_reviews_final": "(status = 'final') = (finalised_at IS NOT NULL)",
}


def upgrade() -> None:
    if not op.get_context().as_sql and "monthly_reviews" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "monthly_reviews",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("status", sa.String(8), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("narrative", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finalised_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalised_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("month", name="uq_monthly_reviews_month"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM monthly_reviews WHERE status = 'final' LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0163_monthly_reviews: final reviews exist. Export them deliberately first.")
    op.drop_table("monthly_reviews")
