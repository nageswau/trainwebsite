"""Add school_staff_assignments, school_career_records, school_psychometric_records,
school_academic_results, school_result_status_history (SCH-004/005/006).

Revision ID: 0026_school_service_delivery
Revises: 0025_school_roster_upload

`DATA_MODEL.md` §6.14/§6.16/§6.17/§6.18. Net-new -- portfolio scoping for the three
specialized School-domain roles (`DEC-SCOPE-013`), and the three service-delivery content
tables: Career Guidance & Counselling (`SCH-004`), Psychometric Assessment (`SCH-005`), and
Academic Results with its Draft->Verified->Published gate + same-actor restriction
(`SCH-006`, `DEC-ROLE-007`).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0026_school_service_delivery"
down_revision = "0025_school_roster_upload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = inspector.get_table_names()

    if "school_staff_assignments" not in existing:
        op.create_table(
            "school_staff_assignments",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id"), nullable=False),
            sa.Column("role", sa.String(50), nullable=False),
            sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "school_id", name="uq_school_staff_assignment"),
        )
        op.create_index("ix_school_staff_assignments_user_id", "school_staff_assignments", ["user_id"])
        op.create_index("ix_school_staff_assignments_school_id", "school_staff_assignments", ["school_id"])

    if "school_career_records" not in existing:
        op.create_table(
            "school_career_records",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
            sa.Column("career_counselor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("record_type", sa.String(30), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_school_career_records_school_student_id", "school_career_records", ["school_student_id"])

    if "school_psychometric_records" not in existing:
        op.create_table(
            "school_psychometric_records",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
            sa.Column("psychometric_team_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("assessment_type", sa.String(120), nullable=False),
            sa.Column("report_url", sa.String(500), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="assigned"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_school_psychometric_records_school_student_id", "school_psychometric_records", ["school_student_id"])

    if "school_academic_results" not in existing:
        op.create_table(
            "school_academic_results",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
            sa.Column("academic_year", sa.String(20), nullable=False),
            sa.Column("term", sa.String(40), nullable=False),
            sa.Column("subject", sa.String(80), nullable=False),
            sa.Column("max_marks", sa.Numeric(6, 2), nullable=False),
            sa.Column("marks_obtained", sa.Numeric(6, 2), nullable=False),
            sa.Column("grade", sa.String(10), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("verified_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_school_academic_results_school_student_id", "school_academic_results", ["school_student_id"])

    if "school_result_status_history" not in existing:
        op.create_table(
            "school_result_status_history",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("result_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_academic_results.id"), nullable=False),
            sa.Column("from_status", sa.String(20), nullable=False),
            sa.Column("to_status", sa.String(20), nullable=False),
            sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_school_result_status_history_result_id", "school_result_status_history", ["result_id"])


def downgrade() -> None:
    op.drop_table("school_result_status_history")
    op.drop_table("school_academic_results")
    op.drop_table("school_psychometric_records")
    op.drop_table("school_career_records")
    op.drop_table("school_staff_assignments")
