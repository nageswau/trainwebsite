"""rec-004 -- company_contacts: many people per company, at most one primary.

Revision ID: 0107_company_contacts
Revises: 0106_rec_companies

docs/superpowers/specs/2026-10-08-rec-004-company-contacts-design.md §2 (DEC-SCOPE-123). A new table only; no existing row changes.
0001 builds a fresh database from the current models, which already carry this table, so it is created only when missing (0069's
idiom). downgrade() refuses while any contact exists: entered data is never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0107_company_contacts"
down_revision = "0106_rec_companies"
branch_labels = None
depends_on = None

TABLE = "company_contacts"
UUID = postgresql.UUID(as_uuid=True)
CHECKS = {  # must equal app.models.COMPANY_CONTACT_CHECKS (test_rec_004_migration)
    "ck_company_contacts_channel": "preferred_channel IS NULL OR preferred_channel IN ('call', 'whatsapp', 'email')",
    "ck_company_contacts_primary_active": "NOT is_primary OR active",
}
INDEXES = {"ix_company_contacts_company": "company_id", "ix_company_contacts_mobile": "mobile_normalized"}
PRIMARY = "uq_company_contacts_primary"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("designation", sa.String(120), nullable=True),
        sa.Column("department", sa.String(120), nullable=True),
        sa.Column("role_id", UUID, sa.ForeignKey("rec_contact_roles.id"), nullable=True),
        sa.Column("mobile", sa.String(40), nullable=True),
        sa.Column("mobile_normalized", sa.String(20), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("linkedin_url", sa.String(300), nullable=True),
        sa.Column("preferred_channel", sa.String(16), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    for name, column in INDEXES.items():
        op.create_index(name, TABLE, [column])
    op.create_index(PRIMARY, TABLE, ["company_id"], unique=True, postgresql_where=sa.text("is_primary"))


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0107_company_contacts: company contacts exist. Clear them deliberately first.")
    op.drop_table(TABLE)
