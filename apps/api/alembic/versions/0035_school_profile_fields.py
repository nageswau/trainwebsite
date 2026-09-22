"""Add School Profile fields (ENH-009, DEC-SCOPE-023).

Revision ID: 0035_school_profile_fields
Revises: 0034_school_transfer_requests

docs/superpowers/specs/2026-09-22-enh-009-school-profile-design.md §2. Additive only: 13 new
nullable columns on the existing `schools` table plus a unique index on `school_code`. No existing
column is altered, no existing row is read or written -- there is nothing to backfill.
`downgrade()` drops the index and all 13 columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0035_school_profile_fields"
down_revision = "0034_school_transfer_requests"
branch_labels = None
depends_on = None

_NEW_COLUMNS = [
    ("school_code", sa.String(8)),
    ("branch", sa.String(200)),
    ("address", sa.String(500)),
    ("contact_number", sa.String(30)),
    ("email", sa.String(255)),
    ("website", sa.String(255)),
    ("grades_available", sa.String(200)),
    ("board", sa.String(20)),
    ("partnership_date", sa.Date()),
    ("mou_reference", sa.String(255)),
    ("edusphere_bdm", sa.String(200)),
    ("monthly_visit_schedule", sa.String(200)),
    ("vice_principal_name", sa.String(200)),
]


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {c["name"] for c in inspector.get_columns("schools")}
    for name, col_type in _NEW_COLUMNS:
        if name not in existing:
            op.add_column("schools", sa.Column(name, col_type, nullable=True))
    existing_indexes = {i["name"] for i in inspector.get_indexes("schools")}
    if "ix_schools_school_code" not in existing_indexes:
        op.create_index("ix_schools_school_code", "schools", ["school_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_schools_school_code", table_name="schools")
    for name, _ in reversed(_NEW_COLUMNS):
        op.drop_column("schools", name)
