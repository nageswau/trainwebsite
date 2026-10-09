"""upc-012 -- partnership_message_templates, university_calls and university_messages.

Revision ID: 0123_university_comms
Revises: 0122_candidate_skills

docs/superpowers/specs/2026-10-09-upc-012-university-comms-design.md §2 (DEC-SCOPE-138). Three new tables; no existing row changes and no
seed (UC4: the head writes the templates). 0001 builds a fresh database from the current models, which already carry these tables, so
creation is guarded (0110's idiom). The CHECKS repeat app.models (test_upc_012_migration). downgrade() refuses while any template, call or
message exists: entered data is never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0123_university_comms"
down_revision = "0122_candidate_skills"
branch_labels = None
depends_on = None

TEMPLATES, CALLS, MESSAGES = "partnership_message_templates", "university_calls", "university_messages"
UUID = postgresql.UUID(as_uuid=True)
OUTCOMES = ("connected", "call_back_requested", "busy", "no_answer", "switched_off", "wrong_number")
TEMPLATE_CHECKS = {  # must equal app.models.PARTNERSHIP_TEMPLATE_CHECKS
    "ck_partnership_message_templates_channel": "channel IN ('whatsapp', 'email')",
    "ck_partnership_message_templates_subject": "(channel = 'email') = (subject IS NOT NULL)",
}
CALL_CHECKS = {  # must equal app.models.UNIVERSITY_CALL_CHECKS
    "ck_university_calls_outcome": f"outcome IN ({', '.join(repr(o) for o in OUTCOMES)})",
    "ck_university_calls_direction": "direction IN ('outgoing', 'incoming')",
    "ck_university_calls_duration": "duration_seconds IS NULL OR duration_seconds BETWEEN 0 AND 14400",
}
MESSAGE_CHECKS = {  # must equal app.models.UNIVERSITY_MESSAGE_CHECKS
    "ck_university_messages_channel": "channel IN ('whatsapp', 'email')",
    "ck_university_messages_email": "(channel = 'email') = (delivery_status IS NOT NULL) AND (channel = 'email') = (subject IS NOT NULL)",
    "ck_university_messages_status": "delivery_status IS NULL OR delivery_status IN ('queued', 'sending', 'retrying', 'sent', 'failed')",
}
INDEXES = {
    "ix_university_calls_university_occurred": (CALLS, ["university_id", "occurred_at"]),
    "ix_university_calls_contact_occurred": (CALLS, ["contact_id", "occurred_at"]),
    "ix_university_calls_caller_occurred": (CALLS, ["caller_user_id", "occurred_at"]),
    "ix_university_messages_university_sent": (MESSAGES, ["university_id", "sent_at"]),
    "ix_university_messages_contact_sent": (MESSAGES, ["contact_id", "sent_at"]),
    "ix_university_messages_sender_sent": (MESSAGES, ["sender_user_id", "sent_at"]),
}


def upgrade() -> None:
    if not op.get_context().as_sql and TEMPLATES in sa.inspect(op.get_bind()).get_table_names():
        return
    when = sa.DateTime(timezone=True)

    def stamps():
        return (sa.Column("created_at", when, server_default=sa.func.now(), nullable=False), sa.Column("updated_at", when, server_default=sa.func.now(), nullable=False))

    def fk(target: str, ondelete: str = "RESTRICT"):
        return sa.ForeignKey(target, ondelete=ondelete)

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
    op.create_index("uq_partnership_message_templates_channel_name", TEMPLATES, ["channel", sa.text("lower(name)")], unique=True)
    op.create_table(
        CALLS,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("university_id", UUID, fk("universities.id"), nullable=False),
        sa.Column("contact_id", UUID, fk("university_contacts.id", "SET NULL"), nullable=True),
        sa.Column("caller_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("occurred_at", when, nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("next_follow_up_on", sa.Date(), nullable=True),
        *stamps(),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CALL_CHECKS.items()),
    )
    op.create_table(
        MESSAGES,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("university_id", UUID, fk("universities.id"), nullable=False),
        sa.Column("contact_id", UUID, fk("university_contacts.id", "SET NULL"), nullable=True),
        sa.Column("sender_user_id", UUID, fk("users.id"), nullable=False),
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
    for name, (table, columns) in INDEXES.items():
        op.create_index(name, table, columns)


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        if any(bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() for table in (TEMPLATES, CALLS, MESSAGES)):
            raise RuntimeError("Cannot downgrade 0123_university_comms: partnership templates, university calls or messages exist. Clear them deliberately first.")
    op.drop_table(MESSAGES)
    op.drop_table(CALLS)
    op.drop_table(TEMPLATES)
