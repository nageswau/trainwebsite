"""hrc-022 -- external candidate portal identity: `user_verification_tokens` and the one-row `candidate_self_service_settings`.

Revision ID: 0261_candidate_portal
Revises: 0260_candidate_profile

docs/superpowers/specs/2026-11-04-hrc-022-candidate-portal-identity-design.md (DEC-SCOPE-384). Two new tables; the `candidate` role is a
value of the free-text `users.role`, so no column changes. 0001 builds a fresh database from the current models, which already carry the
tables, so each step runs only when missing (0251's idiom). The checks are frozen copies of the model's strings at this revision. No
existing row is touched; the downgrade drops the two tables.
"""

import sqlalchemy as sa

from alembic import op

revision = "0261_candidate_portal"
down_revision = "0260_candidate_profile"
branch_labels = None
depends_on = None

TOKEN_CHECKS = {
    "ck_user_verification_tokens_purpose": "purpose IN ('verify_email', 'email_change')",
    "ck_user_verification_tokens_new_email": "(purpose = 'email_change') = (new_email IS NOT NULL)",
}


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "user_verification_tokens" not in tables:
        op.create_table(
            "user_verification_tokens",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("purpose", sa.String(20), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("new_email", sa.String(255), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in TOKEN_CHECKS.items()),
        )
        op.create_index("ix_user_verification_tokens_user", "user_verification_tokens", ["user_id", "purpose", "created_at"])
    if "candidate_self_service_settings" not in tables:
        op.create_table(
            "candidate_self_service_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("fields", sa.JSON(), nullable=False),
            sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint("id = 1", name="ck_candidate_self_service_settings_one_row"),
        )


def downgrade() -> None:
    op.drop_table("candidate_self_service_settings")
    op.drop_table("user_verification_tokens")
