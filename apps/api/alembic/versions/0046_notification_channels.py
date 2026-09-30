"""ENH-014 -- notification channel preferences and the delivery render context.

Revision ID: 0046_notification_channels
Revises: 0045_psychometric_result_fields

docs/superpowers/specs/2026-09-30-enh-014-notification-channels-design.md §4 (DEC-NOT-001, 2026-09-30 extension).
Additive only: one new table, one nullable column, one index. No existing row is touched. `downgrade()` drops exactly
these three. Guarded like 0045: on a fresh database 0001_initial's create_all() has already built them from the models.
If another branch merges a 0046 first, re-chain this one on top of it (precedent: 0045's note).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0046_notification_channels"
down_revision = "0045_psychometric_result_fields"
branch_labels = None
depends_on = None

TABLE = "notification_preferences"
DELIVERIES = "notification_deliveries"
INDEX = "ix_notification_deliveries_status_updated_at"


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    if offline or TABLE not in inspector.get_table_names():
        op.create_table(
            TABLE,
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("whatsapp_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sms_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("whatsapp_opted_in_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sms_opted_in_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if offline or "context" not in {c["name"] for c in inspector.get_columns(DELIVERIES)}:
        op.add_column(DELIVERIES, sa.Column("context", postgresql.JSON(), nullable=True))
    if offline or INDEX not in {i["name"] for i in inspector.get_indexes(DELIVERIES)}:
        op.create_index(INDEX, DELIVERIES, ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name=DELIVERIES)
    op.drop_column(DELIVERIES, "context")
    op.drop_table(TABLE)
