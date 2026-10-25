"""ccrm-037 -- counselor_message_templates and student_messages.

Revision ID: 0191_student_messages
Revises: 0190_overdue_escalation

docs/superpowers/specs/2026-10-25-ccrm-037-counselor-student-messages-design.md (DEC-SCOPE-273). Two new tables; no existing row changes and
no seed (MT1: the Overseas Admin writes the templates). 0001 builds a fresh database from the current models, which already carry these
tables, so creation is guarded (0125's idiom). The CHECKS repeat app.models (test_ccrm_037_migration). downgrade() refuses while any template
or message exists: entered data is never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0191_student_messages"
down_revision = "0190_overdue_escalation"
branch_labels = None
depends_on = None

TEMPLATES, MESSAGES = "counselor_message_templates", "student_messages"
UUID = postgresql.UUID(as_uuid=True)
TEMPLATE_CHECKS = {  # must equal app.models.COUNSELOR_TEMPLATE_CHECKS
    "ck_counselor_message_templates_channel": "channel IN ('whatsapp', 'email')",
    "ck_counselor_message_templates_subject": "(channel = 'email') = (subject IS NOT NULL)",
}
MESSAGE_CHECKS = {  # must equal app.models.STUDENT_MESSAGE_CHECKS
    "ck_student_messages_channel": "channel IN ('whatsapp', 'email')",
    "ck_student_messages_direction": "direction IN ('outbound', 'inbound')",
    "ck_student_messages_status": "delivery_status IS NULL OR delivery_status IN ('queued', 'sending', 'retrying', 'sent', 'failed')",
    "ck_student_messages_outbound_email": ("direction <> 'outbound' OR ((channel = 'email') = (delivery_status IS NOT NULL) AND (channel = 'email') = (subject IS NOT NULL))"),
    "ck_student_messages_inbound": "direction <> 'inbound' OR (delivery_status IS NULL AND template_id IS NULL AND (channel = 'email' OR subject IS NULL))",
}
INDEXES = {
    "ix_student_messages_student_sent": ["student_user_id", "sent_at"],
    "ix_student_messages_application_sent": ["application_id", "sent_at"],
    "ix_student_messages_sender_sent": ["sender_user_id", "sent_at"],
}


def upgrade() -> None:
    if not op.get_context().as_sql and TEMPLATES in sa.inspect(op.get_bind()).get_table_names():
        return
    when = sa.DateTime(timezone=True)

    def stamps():
        return (sa.Column("created_at", when, server_default=sa.func.now(), nullable=False), sa.Column("updated_at", when, server_default=sa.func.now(), nullable=False))

    def fk(target: str):
        return sa.ForeignKey(target, ondelete="RESTRICT")

    op.create_table(
        TEMPLATES,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("subject", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *stamps(),
        *(sa.CheckConstraint(sql, name=name) for name, sql in TEMPLATE_CHECKS.items()),
    )
    op.create_index("uq_counselor_message_templates_channel_name", TEMPLATES, ["channel", sa.text("lower(name)")], unique=True)
    op.create_table(
        MESSAGES,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("student_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("application_id", UUID, fk("overseas_applications.id"), nullable=True),
        sa.Column("sender_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("template_id", UUID, fk(f"{TEMPLATES}.id"), nullable=True),
        sa.Column("template_name", sa.String(160), nullable=True),
        sa.Column("subject", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("delivery_status", sa.String(16), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sent_at", when, nullable=False),
        *stamps(),
        *(sa.CheckConstraint(sql, name=name) for name, sql in MESSAGE_CHECKS.items()),
    )
    for name, columns in INDEXES.items():
        op.create_index(name, MESSAGES, columns)


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        if any(bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() for table in (TEMPLATES, MESSAGES)):
            raise RuntimeError("Cannot downgrade 0191_student_messages: counselor templates or student messages exist. Clear them deliberately first.")
    op.drop_table(MESSAGES)
    op.drop_table(TEMPLATES)
