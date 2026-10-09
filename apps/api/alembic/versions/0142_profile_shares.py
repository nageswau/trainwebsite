"""rec-019 -- profile sharing: profile_shares and profile_share_items.

Revision ID: 0142_profile_shares
Revises: 0141_talent_pools

docs/superpowers/specs/2026-10-09-rec-019-profile-sharing-design.md §2 (DEC-SCOPE-160). Additive: two new tables, no existing row read or
written. 0001 builds a fresh database from the current models, which already carry both tables, so each is created only when missing.
CHANNELS / RESPONSES / *_CHECKS are frozen copies of app.models.PROFILE_SHARE_* (test_rec_019_migration). downgrade() refuses while any
share exists: what was sent to a company is never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0142_profile_shares"
down_revision = "0141_talent_pools"
branch_labels = None
depends_on = None

SHARES = "profile_shares"
ITEMS = "profile_share_items"
CHANNELS = ("email", "whatsapp", "portal", "other")
RESPONSES = ("pending", "interested", "not_interested", "interview_requested")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


SHARE_CHECKS = {
    "ck_profile_shares_channel": _in_list("channel", CHANNELS),
    "ck_profile_shares_message": "(channel IN ('email', 'whatsapp')) = (message_id IS NOT NULL) AND (channel NOT IN ('email', 'whatsapp') OR contact_id IS NOT NULL)",
    "ck_profile_shares_note": "note IS NULL OR char_length(note) <= 500",
}
ITEM_CHECKS = {
    "ck_profile_share_items_response": _in_list("response", RESPONSES),
    "ck_profile_share_items_token": "(token_hash IS NULL) = (token_expires_at IS NULL)",
    "ck_profile_share_items_feedback": "feedback IS NULL OR char_length(feedback) <= 1000",
}


def _tables() -> set[str]:
    if op.get_context().as_sql:  # offline SQL: emit everything
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def _fk(target: str) -> sa.ForeignKey:
    return sa.ForeignKey(target, ondelete="RESTRICT")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    tables = _tables()
    uuid = postgresql.UUID(as_uuid=True)
    if SHARES not in tables:
        op.create_table(
            SHARES,
            sa.Column("id", uuid, primary_key=True),
            sa.Column("job_id", uuid, _fk("jobs.id"), nullable=False),
            sa.Column("company_id", uuid, _fk("companies.id"), nullable=False),
            sa.Column("contact_id", uuid, _fk("company_contacts.id"), nullable=True),
            sa.Column("channel", sa.String(16), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("message_id", uuid, _fk("recruiter_messages.id"), nullable=True),
            sa.Column("shared_by_user_id", uuid, _fk("users.id"), nullable=False),
            *_timestamps(),
            *(sa.CheckConstraint(sql, name=name) for name, sql in SHARE_CHECKS.items()),
        )
        op.create_index("ix_profile_shares_job", SHARES, ["job_id", "created_at"])
        op.create_index("ix_profile_shares_company", SHARES, ["company_id", "created_at"])
    if ITEMS not in tables:
        op.create_table(
            ITEMS,
            sa.Column("id", uuid, primary_key=True),
            sa.Column("share_id", uuid, _fk("profile_shares.id"), nullable=False),
            sa.Column("candidate_id", uuid, _fk("candidates.id"), nullable=False),
            sa.Column("application_id", uuid, _fk("job_applications.id"), nullable=False),
            sa.Column("resume_id", uuid, _fk("candidate_resumes.id"), nullable=True),
            sa.Column("token_hash", sa.String(64), nullable=True),
            sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("response", sa.String(24), nullable=False, server_default="pending"),
            sa.Column("feedback", sa.Text(), nullable=True),
            sa.Column("responded_by_user_id", uuid, _fk("users.id"), nullable=True),
            sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
            *_timestamps(),
            sa.UniqueConstraint("share_id", "candidate_id", name="uq_profile_share_items_candidate"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in ITEM_CHECKS.items()),
        )
        op.create_index("ix_profile_share_items_candidate", ITEMS, ["candidate_id"])
        op.create_index("uq_profile_share_items_token", ITEMS, ["token_hash"], unique=True, postgresql_where=sa.text("token_hash IS NOT NULL"))


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {SHARES} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0142_profile_shares: profile shares exist. Clear them deliberately first.")
    op.drop_table(ITEMS)
    op.drop_table(SHARES)
