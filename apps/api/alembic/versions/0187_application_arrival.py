"""ccrm-028 -- arrival and orientation: overseas_applications.arrival_date / arrival_confirmed_at / arrival_confirmed_by_id /
orientation_attended / arrival_notes, and the CHECK that orientation needs a confirmed arrival.

Revision ID: 0187_application_arrival
Revises: 0186_lead_loss_capture

docs/superpowers/specs/2026-10-25-ccrm-028-arrival-orientation-design.md (DEC-SCOPE-265). Additive: existing rows keep NULLs and `false`.
0001 builds a fresh database from the current models, which already carry the columns, so they are added only when missing (0184's
idiom). downgrade() drops them.
"""

import sqlalchemy as sa

from alembic import op

revision = "0187_application_arrival"
down_revision = "0186_lead_loss_capture"
branch_labels = None
depends_on = None

TABLE = "overseas_applications"
FK = "fk_overseas_applications_arrival_confirmed_by_id"
CHECK = "ck_overseas_applications_orientation_arrival"


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    if inspector is None or "arrival_date" not in {c["name"] for c in inspector.get_columns(TABLE)}:
        op.add_column(TABLE, sa.Column("arrival_date", sa.Date(), nullable=True))
        op.add_column(TABLE, sa.Column("arrival_confirmed_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(TABLE, sa.Column("arrival_confirmed_by_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(FK, TABLE, "users", ["arrival_confirmed_by_id"], ["id"], ondelete="SET NULL")
        op.add_column(TABLE, sa.Column("orientation_attended", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        op.add_column(TABLE, sa.Column("arrival_notes", sa.Text(), nullable=True))
        op.create_check_constraint(CHECK, TABLE, "NOT orientation_attended OR arrival_confirmed_at IS NOT NULL")


def downgrade() -> None:
    op.drop_constraint(CHECK, TABLE, type_="check")
    op.drop_column(TABLE, "arrival_notes")
    op.drop_column(TABLE, "orientation_attended")
    op.drop_constraint(FK, TABLE, type_="foreignkey")
    op.drop_column(TABLE, "arrival_confirmed_by_id")
    op.drop_column(TABLE, "arrival_confirmed_at")
    op.drop_column(TABLE, "arrival_date")
