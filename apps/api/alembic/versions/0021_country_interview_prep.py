"""Add Country.interview_prep (VISA-002).

Revision ID: 0021_country_interview_prep
Revises: 0020_audit_log_outcome

The actual interview-prep content is a confirmed open item (`PRODUCT_DECISION_REGISTER.md`
DEC-DATA-001/DEC-SCOPE-006 -- "the actual checklist/interview-prep/tracking rules ...
remain an open item"). Nullable, data-driven per country (matching `Country`'s other
free-text fields), not exposed through the public country schema/endpoint -- only through
the new self-scoped `GET /overseas/visa/interview-prep`.
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_country_interview_prep"
down_revision = "0020_audit_log_outcome"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("countries")}
    if "interview_prep" not in columns:
        op.add_column("countries", sa.Column("interview_prep", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("countries", "interview_prep")
