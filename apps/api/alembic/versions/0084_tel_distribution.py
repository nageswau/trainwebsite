"""tel-007 -- tel_distribution_rules and tel_round_robin_cursors: per-team product/city routing rules and the round-robin cursor.

Revision ID: 0084_tel_distribution
Revises: 0083_tel_content

docs/superpowers/specs/2026-10-06-tel-007-lead-distribution-design.md §3 (DEC-SCOPE-085). Adds two tables; no existing row is read or
written, and existing unassigned leads are not backfilled (DI2). 0001 builds a fresh database from the current models, which already carry
the tables, so creation is guarded (0075's idiom). downgrade() refuses while any rule exists: rules are manager configuration that a
downgrade would silently lose.

Re-chained 2026-10-06 on merging `main` @ `50838192`: drafted as `0082_tel_distribution` on `0081_lead_stage_pipeline` (DEC-SCOPE-082), but
bdm-025's `0082_bdm_assignment_history` (DEC-SCOPE-082) and tel-012's `0083_tel_content` (DEC-SCOPE-083) reached `main` first. A database
stamped at `0082_tel_distribution` is re-stamped with `alembic stamp --purge 0081_lead_stage_pipeline` then `upgrade head` (the create is
guarded, so the re-run is harmless).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0084_tel_distribution"
down_revision = "0083_tel_content"
branch_labels = None
depends_on = None

RULES, CURSORS = "tel_distribution_rules", "tel_round_robin_cursors"


def upgrade() -> None:
    if not op.get_context().as_sql and RULES in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        RULES,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("team", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tel_products.id"), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("telecaller_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("team IN ('it', 'overseas')", name="ck_tel_distribution_rules_team"),
        sa.CheckConstraint("kind IN ('product', 'city')", name="ck_tel_distribution_rules_kind"),
        sa.CheckConstraint(
            "(kind = 'product' AND product_id IS NOT NULL AND city IS NULL) OR (kind = 'city' AND city IS NOT NULL AND product_id IS NULL)",
            name="ck_tel_distribution_rules_shape",
        ),
    )
    op.create_index("uq_tel_distribution_rules_product", RULES, ["team", "product_id"], unique=True, postgresql_where=sa.text("kind = 'product'"))
    op.create_index("uq_tel_distribution_rules_city", RULES, ["team", sa.text("lower(city)")], unique=True, postgresql_where=sa.text("kind = 'city'"))
    op.create_index("ix_tel_distribution_rules_telecaller", RULES, ["telecaller_user_id"])
    op.create_table(
        CURSORS,
        sa.Column("team", sa.String(20), primary_key=True),
        sa.Column("last_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("team IN ('it', 'overseas')", name="ck_tel_round_robin_cursors_team"),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {RULES} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0084_tel_distribution: distribution rules exist (manager configuration). Remove them deliberately first.")
    op.drop_table(CURSORS)
    op.drop_table(RULES)
