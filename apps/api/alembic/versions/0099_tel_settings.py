"""tel-020 -- tel_settings: each team's alert thresholds (Lead Not Contacted, Hot Lead Pending), seeded 24 h / 4 h.

Revision ID: 0099_tel_settings
Revises: 0098_bdm_agent_link

docs/superpowers/specs/2026-10-07-tel-020-alerts-design.md §3 (DEC-SCOPE-111 AL1). Adds one table; no existing row is read or written.
Drafted as 0098_tel_settings on 0097; bdm-019 merged first with 0098_bdm_agent_link, so it is renumbered to 0099 after it.
0001 builds a fresh database from the current models, which already carry the table, so creation is guarded (0080's idiom); the seed
always runs and skips a team that already has a row. DEFAULTS repeats models.TEL_SETTING_DEFAULTS (test_tel_020_migration asserts it).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0099_tel_settings"
down_revision = "0098_bdm_agent_link"
branch_labels = None
depends_on = None

TABLE = "tel_settings"
DEFAULTS = {"not_contacted_hours": 24, "hot_pending_hours": 4}


def upgrade() -> None:
    if op.get_context().as_sql or TABLE not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            TABLE,
            sa.Column("team", sa.String(20), primary_key=True),
            sa.Column("not_contacted_hours", sa.Integer(), nullable=False),
            sa.Column("hot_pending_hours", sa.Integer(), nullable=False),
            sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("team IN ('it', 'overseas')", name="ck_tel_settings_team"),
            *(sa.CheckConstraint(f"{col} BETWEEN 1 AND 168", name=f"ck_tel_settings_{col}") for col in DEFAULTS),
        )
    op.execute(
        f"INSERT INTO {TABLE} (team, not_contacted_hours, hot_pending_hours) VALUES "
        f"('it', {DEFAULTS['not_contacted_hours']}, {DEFAULTS['hot_pending_hours']}), "
        f"('overseas', {DEFAULTS['not_contacted_hours']}, {DEFAULTS['hot_pending_hours']}) ON CONFLICT (team) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table(TABLE)
