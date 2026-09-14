"""Add operational learning, admissions, agent, and meeting workflows.

Revision ID: 0003_operational_workflows
Revises: 0002_assessments
"""
from alembic import op
import sqlalchemy as sa

from app.models import Base

revision = "0003_operational_workflows"
down_revision = "0002_assessments"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _add(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _unique_index(name: str, table: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {index["name"] for index in inspector.get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, unique=True)


def upgrade():
    bind = op.get_bind()

    _add("batches", sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Kolkata"))
    _add("batches", sa.Column("capacity", sa.Integer(), nullable=False, server_default="20"))
    _add("batches", sa.Column("enrollment_open", sa.Boolean(), nullable=False, server_default=sa.true()))

    _add("enrollments", sa.Column("enrollment_code", sa.String(80), nullable=True))
    _add("enrollments", sa.Column("enrolled_on", sa.Date(), nullable=False, server_default=sa.func.current_date()))
    _add("enrollments", sa.Column("slot_locked", sa.Boolean(), nullable=False, server_default=sa.true()))
    enrollment_rows = bind.execute(sa.text("SELECT id FROM enrollments WHERE enrollment_code IS NULL")).fetchall()
    for row in enrollment_rows:
        bind.execute(sa.text("UPDATE enrollments SET enrollment_code=:code WHERE id=:id"), {"code": f"EDU-{row.id:06d}", "id": row.id})
    op.alter_column("enrollments", "enrollment_code", nullable=False)
    _unique_index("ix_enrollments_enrollment_code", "enrollments", ["enrollment_code"])

    _add("assignments", sa.Column("assignment_type", sa.String(30), nullable=False, server_default="assignment"))
    _add("assignments", sa.Column("submission_type", sa.String(30), nullable=False, server_default="text_or_file"))
    _add("assignments", sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.true()))

    _add("assessments", sa.Column("pass_percent", sa.Integer(), nullable=False, server_default="50"))
    _add("assessments", sa.Column("attempts_allowed", sa.Integer(), nullable=False, server_default="1"))
    _add("assessments", sa.Column("instructions", sa.Text(), nullable=False, server_default=""))
    _add("assessments", sa.Column("publish_results", sa.Boolean(), nullable=False, server_default=sa.true()))

    _add("submissions", sa.Column("graded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    _add("submissions", sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True))

    _add("certificates", sa.Column("enrollment_id", sa.Integer(), sa.ForeignKey("enrollments.id"), nullable=True))
    _add("certificates", sa.Column("verification_code", sa.String(80), nullable=True))
    _add("certificates", sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    _add("certificates", sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True))
    _add("certificates", sa.Column("criteria_snapshot", sa.JSON(), nullable=False, server_default="{}"))
    certificate_rows = bind.execute(sa.text("SELECT id, certificate_no FROM certificates WHERE verification_code IS NULL")).fetchall()
    for row in certificate_rows:
        bind.execute(sa.text("UPDATE certificates SET verification_code=:code WHERE id=:id"), {"code": row.certificate_no or f"CERT-{row.id:06d}", "id": row.id})
    op.alter_column("certificates", "verification_code", nullable=False)
    _unique_index("ix_certificates_verification_code", "certificates", ["verification_code"])

    _add("overseas_applications", sa.Column("agent_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    _add("overseas_applications", sa.Column("next_action", sa.Text(), nullable=True))
    _add("student_documents", sa.Column("original_filename", sa.String(255), nullable=True))
    _add("student_documents", sa.Column("content_type", sa.String(120), nullable=True))
    _add("student_documents", sa.Column("file_size", sa.Integer(), nullable=True))

    _add("live_sessions", sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True))
    _add("live_sessions", sa.Column("host_url", sa.String(500), nullable=True))
    _add("live_sessions", sa.Column("provider_event_id", sa.String(200), nullable=True))
    _add("live_sessions", sa.Column("provider_meeting_id", sa.String(200), nullable=True))
    _add("live_sessions", sa.Column("recording_external_id", sa.String(200), nullable=True))
    _add("live_sessions", sa.Column("recording_status", sa.String(30), nullable=False, server_default="not_available"))
    _add("live_sessions", sa.Column("sync_status", sa.String(30), nullable=False, server_default="manual"))

    # Create all newly introduced tables while preserving existing data.
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade():
    for table in (
        "inbound_university_emails", "agent_commissions", "agent_students",
        "notification_deliveries", "application_status_history", "job_offers",
        "placement_profiles", "assessment_answers", "assessment_attempts",
        "assessment_questions", "attendance_corrections",
    ):
        if table in sa.inspect(op.get_bind()).get_table_names():
            op.drop_table(table)
