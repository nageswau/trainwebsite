"""tel-014 -- `lead_messages` carries email sends: an attempt counter and the email delivery-status check.

Revision ID: 0097_lead_message_email
Revises: 0096_bdm_targets

docs/superpowers/specs/2026-10-07-tel-014-email-design.md §2 (DEC-SCOPE-106). Drafted as 0096 on 0095_lead_messages; bdm-016 merged first
with 0096_bdm_targets, so it is renumbered to 0097 after it. 0001 builds a fresh database from the current models, which
already carry the column and the check, so the upgrade is guarded (0095's idiom). CHECK_SQL repeats models.LEAD_MESSAGE_EMAIL_CHECK
(test_tel_014_migration asserts they stay identical). Every existing row is WhatsApp, so the default 0 and the new check hold.
"""

import sqlalchemy as sa

from alembic import op

revision = "0097_lead_message_email"
down_revision = "0096_bdm_targets"
branch_labels = None
depends_on = None

TABLE = "lead_messages"
CHECK_NAME = "ck_lead_messages_email"
CHECK_SQL = "channel <> 'email' OR (subject IS NOT NULL AND delivery_status IS NOT NULL AND delivery_status IN ('queued', 'sending', 'retrying', 'sent', 'failed'))"


def _has_column() -> bool:
    return any(c["name"] == "attempt_count" for c in sa.inspect(op.get_bind()).get_columns(TABLE))


def upgrade() -> None:
    if not op.get_context().as_sql and _has_column():
        return
    op.add_column(TABLE, sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False))
    op.create_check_constraint(CHECK_NAME, TABLE, CHECK_SQL)


def downgrade() -> None:
    op.drop_constraint(CHECK_NAME, TABLE, type_="check")
    op.drop_column(TABLE, "attempt_count")
