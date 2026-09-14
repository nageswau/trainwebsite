"""Add agreements and consent_records (STU-009, DATA_MODEL.md §3.4).

Revision ID: 0008_agreements_consent
Revises: 0007_submission_is_late

DATA_MODEL.md §3.4's own constraint: "Enrollment.status cannot reach `active` without a
matching ConsentRecord (STU-009-AC02)." The base codebase set every new enrolment to
`active` immediately on booking, with no consent step at all. New enrolments now start as
`pending_consent` (see `app/api/workflows.py::create_enrollment`) and only move to
`active` once `POST /workflows/it/student/agreements/{id}/accept` records a ConsentRecord.

Pre-existing `active` enrolments (including seeded demo data) predate this feature and are
grandfathered as-is -- fabricating a ConsentRecord for consent that was never actually
given would misrepresent evidence, which NO-ASSUMPTION MODE forbids.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_agreements_consent"
down_revision = "0007_submission_is_late"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = inspector.get_table_names()

    if "agreements" not in existing:
        op.create_table(
            "agreements",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("division", sa.String(30), nullable=False, server_default="it"),
            sa.Column("version", sa.String(20), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("body", sa.Text, nullable=False),
            sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_agreements_division", "agreements", ["division"])

    if "consent_records" not in existing:
        op.create_table(
            "consent_records",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("agreement_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agreements.id"), nullable=False),
            sa.Column("version", sa.String(20), nullable=False),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "agreement_id", name="uq_consent_user_agreement"),
        )
        op.create_index("ix_consent_records_user_id", "consent_records", ["user_id"])
        op.create_index("ix_consent_records_agreement_id", "consent_records", ["agreement_id"])


def downgrade() -> None:
    op.drop_index("ix_consent_records_agreement_id", table_name="consent_records")
    op.drop_index("ix_consent_records_user_id", table_name="consent_records")
    op.drop_table("consent_records")
    op.drop_index("ix_agreements_division", table_name="agreements")
    op.drop_table("agreements")
