"""tel-013 -- `lead_messages`: WhatsApp (and, from tel-014, email) messages sent to a lead.

Revision ID: 0094_lead_messages
Revises: 0093_bdm_meeting_requests

docs/superpowers/specs/2026-10-07-tel-013-whatsapp-design.md §2 (DEC-SCOPE-099). Drafted on 0092_lead_calls and re-chained after tel-019's
0093_bdm_meeting_requests (DEC-SCOPE-098), which merged first. 0001 builds a fresh database from the current models, which already carry
the table, so the upgrade is guarded (0092's idiom). CHECKS repeats models.LEAD_MESSAGE_CHECKS (test_tel_013_migration
asserts they stay identical).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0094_lead_messages"
down_revision = "0093_bdm_meeting_requests"
branch_labels = None
depends_on = None

TABLE = "lead_messages"
CHECKS = {
    "ck_lead_messages_channel": "channel IN ('whatsapp', 'email')",
    "ck_lead_messages_body": "length(body) BETWEEN 1 AND 5000",
    "ck_lead_messages_whatsapp": "channel <> 'whatsapp' OR (subject IS NULL AND delivery_status IS NULL)",
}


def upgrade() -> None:
    if not op.get_context().as_sql and sa.inspect(op.get_bind()).has_table(TABLE):
        return
    uuid = postgresql.UUID(as_uuid=True)
    when = sa.DateTime(timezone=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("lead_id", uuid, sa.ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sender_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("template_id", uuid, sa.ForeignKey("tel_message_templates.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("template_name", sa.String(160), nullable=True),
        sa.Column("subject", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("delivery_status", sa.String(16), nullable=True),
        sa.Column("sent_at", when, nullable=False),
        sa.Column("created_at", when, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", when, server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_lead_messages_lead_sent", TABLE, ["lead_id", "sent_at"])
    op.create_index("ix_lead_messages_sender_sent", TABLE, ["sender_user_id", "sent_at"])


def downgrade() -> None:
    op.drop_index("ix_lead_messages_sender_sent", table_name=TABLE)
    op.drop_index("ix_lead_messages_lead_sent", table_name=TABLE)
    op.drop_table(TABLE)
