"""Add employer registration (EMP-001).

Revision ID: 0017_employer_registration
Revises: 0016_data_subject_requests

DATA_MODEL.md #5.1/#5.2: `Company` gets `owner_type`/`employer_user_id` (extends the
existing table rather than forking a parallel Employer-owned set -- the Placement-Team-
mediation question, FEATURE_QUESTIONS.md #1, is still open). `EmployerProfile` is net-new;
`registration_status` is nullable/unenforced by design (FEATURE_QUESTIONS.md #7 is open).
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_employer_registration"
down_revision = "0016_data_subject_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("companies")}

    if "owner_type" not in columns:
        op.add_column("companies", sa.Column("owner_type", sa.String(30), nullable=False, server_default="internal"))
    if "employer_user_id" not in columns:
        op.add_column("companies", sa.Column("employer_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))

    if "employer_profiles" not in inspector.get_table_names():
        op.create_table(
            "employer_profiles",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True, index=True),
            sa.Column("company_id", sa.Uuid(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
            sa.Column("registration_status", sa.String(20), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    op.drop_table("employer_profiles")
    op.drop_column("companies", "employer_user_id")
    op.drop_column("companies", "owner_type")
