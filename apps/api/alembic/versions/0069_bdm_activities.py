"""bdm-009 -- bdm_activities.

Revision ID: 0069_bdm_activities
Revises: 0068_bdm_trips

docs/superpowers/specs/2026-10-03-bdm-009-activity-log-design.md §4 (DEC-SCOPE-065). Additive: one table; no existing row is read or
written. 0001 builds a fresh database from the current models, which already carry it, so creation is guarded (0061's idiom).
downgrade() refuses while activities exist: they are the only record of each call, message and visit.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0069_bdm_activities"
down_revision = "0068_bdm_trips"
branch_labels = None
depends_on = None

TABLE = "bdm_activities"
CHANNELS = "'call', 'whatsapp', 'email', 'visit', 'meeting', 'other'"
DIRECTIONAL = "'call', 'whatsapp', 'email'"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("bdm_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("organization_id", uuid, sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contact_id", uuid, sa.ForeignKey("bdm_organization_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"channel IN ({CHANNELS})", name="ck_bdm_activities_channel"),
        sa.CheckConstraint("direction IS NULL OR direction IN ('outbound', 'inbound')", name="ck_bdm_activities_direction"),
        sa.CheckConstraint(f"(channel IN ({DIRECTIONAL})) = (direction IS NOT NULL)", name="ck_bdm_activities_direction_channel"),
    )
    op.create_index("ix_bdm_activities_bdm_user_id_occurred_at", TABLE, ["bdm_user_id", "occurred_at"])
    op.create_index("ix_bdm_activities_organization_id_occurred_at", TABLE, ["organization_id", "occurred_at"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0069_bdm_activities: BDM activities exist. Remove them deliberately first.")
    op.drop_table(TABLE)
