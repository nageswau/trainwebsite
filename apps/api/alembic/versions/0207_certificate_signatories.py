"""nehn-032 -- certificate signatures: `certificate_signatories` and `certificates.signatory_snapshot`.

Revision ID: 0207_certificate_signatories
Revises: 0204_certificate_workflow

docs/superpowers/specs/2026-10-27-nehn-032-certificate-signatures-design.md (DEC-SCOPE-300). 0001 builds a fresh database from the current
models, which already carry the table and the column, so both are created only when missing (0204's idiom). No existing row changes:
issued certificates keep a NULL snapshot. No grant is seeded (`certificates.manage` is super_admin's until granted). The downgrade drops the
column and the table; stored signature images are left in storage.
"""

import sqlalchemy as sa

from alembic import op

revision = "0207_certificate_signatories"
down_revision = "0204_certificate_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    if offline or "certificate_signatories" not in inspector.get_table_names():
        op.create_table(
            "certificate_signatories",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("display_name", sa.String(120), nullable=False),
            sa.Column("designation", sa.String(120), nullable=False),
            sa.Column("image_key", sa.String(200), nullable=False),
            sa.Column("active_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("active_to", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("role IN ('founder', 'coordinator')", name="ck_certificate_signatories_role"),
        )
        op.create_index("uq_certificate_signatories_active_role", "certificate_signatories", ["role"], unique=True, postgresql_where=sa.text("active_to IS NULL"))
    if offline or "signatory_snapshot" not in {c["name"] for c in inspector.get_columns("certificates")}:
        op.add_column("certificates", sa.Column("signatory_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.execute("ALTER TABLE certificates DROP COLUMN IF EXISTS signatory_snapshot")
    op.execute("DROP TABLE IF EXISTS certificate_signatories")
