"""ENH-003 -- password_reset_tokens.purpose + superseded_at (welcome links for admin-provisioned accounts).

Revision ID: 0032_welcome_token_purpose
Revises: 0031_academic_result_remarks

docs/superpowers/specs/2026-09-19-enh-003-first-time-provisioning-design.md §4. Additive only.
`purpose` is NOT NULL with a server default of 'reset', which backfills every existing row without a
rewrite; no index (two values, no selectivity -- the user_id index already serves the queries).
"""

from alembic import op
import sqlalchemy as sa

revision = "0032_welcome_token_purpose"
down_revision = "0031_academic_result_remarks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {c["name"] for c in inspector.get_columns("password_reset_tokens")}
    if "purpose" not in existing:
        op.add_column("password_reset_tokens", sa.Column("purpose", sa.String(20), nullable=False, server_default="reset"))
    if "superseded_at" not in existing:
        op.add_column("password_reset_tokens", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("password_reset_tokens", "superseded_at")
    op.drop_column("password_reset_tokens", "purpose")
