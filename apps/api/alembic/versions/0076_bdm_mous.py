"""bdm-005 -- MoU tracking: bdm_mous and bdm_mou_events.

Revision ID: 0076_bdm_mous
Revises: 0075_telecaller_profiles

docs/superpowers/specs/2026-10-06-bdm-005-mou-tracking-design.md §5 (DEC-SCOPE-074). Additive: two new tables, no existing row read
or written. 0001 builds a fresh database from the current models, which already carry both tables, so each is created only when
missing. STATUSES / EVENT_KINDS are frozen copies of app.models.BDM_MOU_SETTABLE / BDM_MOU_EVENT_KINDS and CHECKS must equal
app.models.BDM_MOU_CHECKS (test_bdm_005_migration). downgrade() refuses while any MoU exists: recorded agreements are never dropped
silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0076_bdm_mous"
down_revision = "0075_telecaller_profiles"
branch_labels = None
depends_on = None

MOUS = "bdm_mous"
EVENTS = "bdm_mou_events"
STATUSES = ("prospect", "discussion_started", "proposal_sent", "under_negotiation", "draft_shared", "signed", "active", "rejected")
EVENT_KINDS = ("created", "status", "updated", "document", "renewed")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {
    "ck_bdm_mous_status": _in_list("status", STATUSES),
    "ck_bdm_mous_window": "valid_from IS NULL OR valid_until IS NULL OR valid_until >= valid_from",
    "ck_bdm_mous_signed_on": "status NOT IN ('signed', 'active') OR signed_on IS NOT NULL",
    "ck_bdm_mous_active_window": "status <> 'active' OR (valid_from IS NOT NULL AND valid_until IS NOT NULL)",
    "ck_bdm_mous_document": "(document_key IS NULL) = (document_content_type IS NULL)",
}


def _tables() -> set[str]:
    if op.get_context().as_sql:  # offline SQL: emit everything
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    uuid = postgresql.UUID(as_uuid=True)
    if MOUS not in tables:
        op.create_table(
            MOUS,
            sa.Column("id", uuid, primary_key=True),
            sa.Column("organization_id", uuid, sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="prospect"),
            sa.Column("status_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("proposal_sent_on", sa.Date(), nullable=True),
            sa.Column("signed_on", sa.Date(), nullable=True),
            sa.Column("valid_from", sa.Date(), nullable=True),
            sa.Column("valid_until", sa.Date(), nullable=True),
            sa.Column("reference", sa.String(100), nullable=True),
            sa.Column("notes", sa.String(2000), nullable=True),
            sa.Column("document_key", sa.String(200), nullable=True),
            sa.Column("document_content_type", sa.String(50), nullable=True),
            sa.Column("document_name", sa.String(255), nullable=True),
            sa.Column("document_uploaded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        )
        op.create_index("uq_bdm_mous_current", MOUS, ["organization_id"], unique=True, postgresql_where=sa.text("is_current"))
        op.create_index("ix_bdm_mous_org", MOUS, ["organization_id", "created_at"])
        op.create_index("ix_bdm_mous_status", MOUS, ["status", "valid_until"])
    if EVENTS not in tables:
        op.create_table(
            EVENTS,
            sa.Column("id", uuid, primary_key=True),
            sa.Column("mou_id", uuid, sa.ForeignKey("bdm_mous.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("actor_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("from_status", sa.String(20), nullable=True),
            sa.Column("to_status", sa.String(20), nullable=False),
            sa.Column("changed", sa.JSON(), nullable=False),
            sa.Column("document_key", sa.String(200), nullable=True),
            sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(_in_list("kind", EVENT_KINDS), name="ck_bdm_mou_events_kind"),
        )
        op.create_index("ix_bdm_mou_events_mou", EVENTS, ["mou_id", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {MOUS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0076_bdm_mous: MoU data exists. Clear it deliberately first.")
    op.drop_table(EVENTS)
    op.drop_table(MOUS)
