"""ENH-012 -- portfolio_entries and portfolio_profiles.

Revision ID: 0035_portfolio
Revises: 0034_school_transfer_requests

docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md §5. Create-table only: no existing
table is altered and no existing row is read or written. `downgrade()` drops both tables.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0035_portfolio"
down_revision = "0034_school_transfer_requests"
branch_labels = None
depends_on = None

ENTRIES_TABLE = "portfolio_entries"
PROFILES_TABLE = "portfolio_profiles"


def upgrade() -> None:
    if not op.get_context().as_sql and ENTRIES_TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        ENTRIES_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
        sa.Column("section", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("organization", sa.String(200), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_portfolio_entries_student_section", ENTRIES_TABLE, ["school_student_id", "section"])
    op.create_table(
        PROFILES_TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False, unique=True),
        sa.Column("personal_statement", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_portfolio_profiles_student", PROFILES_TABLE, ["school_student_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_portfolio_profiles_student", table_name=PROFILES_TABLE)
    op.drop_table(PROFILES_TABLE)
    op.drop_index("ix_portfolio_entries_student_section", table_name=ENTRIES_TABLE)
    op.drop_table(ENTRIES_TABLE)
