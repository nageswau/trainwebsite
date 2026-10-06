"""tel-006 -- `lead_import_batches`: one CSV lead import for a campaign.

Revision ID: 0087_lead_import_batches
Revises: 0086_lead_enquiries

docs/superpowers/specs/2026-10-06-tel-006-lead-import-design.md §2 (DEC-SCOPE-091). The uploaded file is never stored (R9): the batch keeps
its SHA-256, the counts and each row's outcome, which give the Idempotency-Key replay (R8). 0001 builds a fresh database from the current
models, which already carry the table, so the upgrade is guarded (0074's idiom).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0087_lead_import_batches"
down_revision = "0086_lead_enquiries"
branch_labels = None
depends_on = None

TABLE = "lead_import_batches"


def upgrade() -> None:
    if not op.get_context().as_sql and sa.inspect(op.get_bind()).has_table(TABLE):
        return
    uuid = postgresql.UUID(as_uuid=True)
    count = {"nullable": False, "server_default": sa.text("0")}
    op.create_table(
        TABLE,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("campaign_id", uuid, sa.ForeignKey("tel_campaigns.id"), nullable=False),
        sa.Column("division", sa.String(20), nullable=False),
        sa.Column("uploaded_by_user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("total_rows", sa.Integer(), **count),
        sa.Column("created_count", sa.Integer(), **count),
        sa.Column("attached_count", sa.Integer(), **count),
        sa.Column("rejected_count", sa.Integer(), **count),
        sa.Column("results_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("uploaded_by_user_id", "idempotency_key", name="uq_lead_import_batches_key"),
        sa.CheckConstraint("division IN ('it', 'overseas')", name="ck_lead_import_batches_division"),
        sa.CheckConstraint("created_count + attached_count + rejected_count = total_rows", name="ck_lead_import_batches_counts"),
    )
    op.create_index("ix_lead_import_batches_uploader", TABLE, ["uploaded_by_user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_lead_import_batches_uploader", table_name=TABLE)
    op.drop_table(TABLE)
