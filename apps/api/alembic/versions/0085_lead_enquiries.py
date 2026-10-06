"""tel-005 -- `lead_enquiries` (an enquiry added to an existing lead) and a nullable `enquiries.email`.

Revision ID: 0085_lead_enquiries
Revises: 0084_bdm_onboarding

docs/superpowers/specs/2026-10-06-tel-005-lead-intake-design.md §2 (DEC-SCOPE-087). I1 (Q-03): a manual lead needs a mobile, not an
email, so `enquiries.email` drops NOT NULL (the website form still requires one). 0001 builds a fresh database from the current models,
which already carry both, so the upgrade is guarded (0074's idiom). downgrade() writes '' into a null email before NOT NULL returns.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0085_lead_enquiries"
down_revision = "0084_bdm_onboarding"
branch_labels = None
depends_on = None

TABLE = "lead_enquiries"
# Frozen copy of app/tel_sources.TEL_SOURCES; test_tel_005_migration asserts it stays identical.
SOURCES = ("instagram", "facebook", "google", "website", "whatsapp", "walk_in", "college", "school", "agent", "referral", "exhibition_event",
           "bdm", "other")
SOURCE_CHECK = f"source IN ({', '.join(repr(s) for s in SOURCES)})"


def upgrade() -> None:
    if not op.get_context().as_sql and sa.inspect(op.get_bind()).has_table(TABLE):
        return
    op.alter_column("enquiries", "email", existing_type=sa.String(255), nullable=True)
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("lead_id", uuid, sa.ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("subject", sa.String(180), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("campaign_id", uuid, sa.ForeignKey("tel_campaigns.id"), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(SOURCE_CHECK, name="ck_lead_enquiries_source"),
    )
    op.create_index("ix_lead_enquiries_lead", TABLE, ["lead_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_lead_enquiries_lead", table_name=TABLE)
    op.drop_table(TABLE)
    op.execute("UPDATE enquiries SET email = '' WHERE email IS NULL")
    op.alter_column("enquiries", "email", existing_type=sa.String(255), nullable=False)
