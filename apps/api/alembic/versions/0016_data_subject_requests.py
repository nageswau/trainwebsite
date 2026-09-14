"""Add data_subject_requests (SEC-002).

Revision ID: 0016_data_subject_requests
Revises: 0015_notification_attempts

SEC-002 -- GDPR self-service export/delete. DATA_MODEL.md #7.4 names two conceptual tables
(DataExportRequest/DataDeletionRequest) but describes one shared field set, and
API_CONTRACT.md #11 exposes a single endpoint family keyed by `type` -- implemented here as
one table with a `type` discriminator, matching the approved API contract. Net-new; no such
table existed before.
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_data_subject_requests"
down_revision = "0015_notification_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "data_subject_requests" in inspector.get_table_names():
        return

    op.create_table(
        "data_subject_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("requesting_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("export_key", sa.String(300), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fulfilled_by_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("requesting_user_id", "idempotency_key", name="uq_data_subject_request_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("data_subject_requests")
