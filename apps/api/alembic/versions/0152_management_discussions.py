"""mgmt-027 -- management discussions & decisions: management_discussions, management_discussion_participants,
management_discussion_attachments.

Revision ID: 0152_management_discussions
Revises: 0151_investments

docs/superpowers/specs/2026-10-12-mgmt-027-discussions-decisions-design.md §3. New tables only; no existing row changes. 0001 builds a
fresh database from the current models, which already carry these tables, so each is created only when missing (0122's idiom).
downgrade() refuses while any discussion exists: recorded management decisions are never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0152_management_discussions"
down_revision = "0151_investments"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
STATUSES = ("open", "in_progress", "completed", "cancelled")  # frozen copy of app.models.DISCUSSION_STATUSES


def _user(name: str, nullable: bool) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def upgrade() -> None:
    existing = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())
    if "management_discussions" not in existing:
        op.create_table(
            "management_discussions",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("topic", sa.String(200), nullable=False),
            sa.Column("discussion_date", sa.Date(), nullable=False),
            sa.Column("department", sa.String(80), nullable=True),
            sa.Column("points", sa.Text(), nullable=True),
            sa.Column("decision", sa.String(500), nullable=True),
            _user("responsible_user_id", True),
            sa.Column("deadline", sa.Date(), nullable=True),
            sa.Column("status", sa.String(12), server_default=sa.text("'open'"), nullable=False),
            sa.Column("follow_up_date", sa.Date(), nullable=True),
            _user("created_by_user_id", False),
            _user("updated_by_user_id", False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(f"status IN ({', '.join(repr(s) for s in STATUSES)})", name="ck_management_discussions_status"),
            sa.CheckConstraint("responsible_user_id IS NULL OR decision IS NOT NULL", name="ck_management_discussions_responsible_decision"),
        )
        op.create_index("ix_management_discussions_date", "management_discussions", ["discussion_date"])
        op.create_index("ix_management_discussions_responsible_status", "management_discussions", ["responsible_user_id", "status"])
        op.create_index("ix_management_discussions_status_deadline", "management_discussions", ["status", "deadline"])
    if "management_discussion_participants" not in existing:
        op.create_table(
            "management_discussion_participants",
            sa.Column("discussion_id", UUID, sa.ForeignKey("management_discussions.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        )
    if "management_discussion_attachments" not in existing:
        op.create_table(
            "management_discussion_attachments",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("discussion_id", UUID, sa.ForeignKey("management_discussions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("storage_key", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(100), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("shareable", sa.Boolean(), server_default=sa.false(), nullable=False),
            _user("uploaded_by_user_id", False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_management_discussion_attachments_discussion", "management_discussion_attachments", ["discussion_id", "created_at"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM management_discussions LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0152_management_discussions: discussions exist. Clear them deliberately first.")
    op.drop_table("management_discussion_attachments")
    op.drop_table("management_discussion_participants")
    op.drop_table("management_discussions")
