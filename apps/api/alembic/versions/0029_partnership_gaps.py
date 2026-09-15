"""School partnership gap-closure: tier, activity_type, Overseas bridge, Test Prep/Language
(DEC-SCOPE-017/018, closes CLIENT_QUESTIONS.md item 9 and DEC-SCOPE-015 item 77/78).

Revision ID: 0029_partnership_gaps
Revises: 0028_student_code

- schools.tier / schools.tier_valid_until (nullable)
- school_activities.activity_type (nullable)
- overseas_applications.student_id relaxed to nullable; overseas_applications.
  school_student_id added (nullable) -- app code enforces exactly one is set
- school_test_prep_records, school_language_records (new tables)

No backfill needed: every new/relaxed column is nullable and every new table starts empty.
"""
from alembic import op
import sqlalchemy as sa

revision = "0029_partnership_gaps"
down_revision = "0028_student_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    school_columns = {c["name"] for c in inspector.get_columns("schools")}
    if "tier" not in school_columns:
        op.add_column("schools", sa.Column("tier", sa.String(20), nullable=True))
        op.add_column("schools", sa.Column("tier_valid_until", sa.Date(), nullable=True))

    activity_columns = {c["name"] for c in inspector.get_columns("school_activities")}
    if "activity_type" not in activity_columns:
        op.add_column("school_activities", sa.Column("activity_type", sa.String(40), nullable=True))

    application_columns = {c["name"] for c in inspector.get_columns("overseas_applications")}
    if "school_student_id" not in application_columns:
        op.alter_column("overseas_applications", "student_id", existing_type=sa.Uuid(as_uuid=True), nullable=True)
        op.add_column("overseas_applications", sa.Column("school_student_id", sa.Uuid(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=True))
        op.create_index("ix_overseas_applications_school_student_id", "overseas_applications", ["school_student_id"])

    if "school_test_prep_records" not in inspector.get_table_names():
        op.create_table(
            "school_test_prep_records",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("school_student_id", sa.Uuid(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
            sa.Column("academic_team_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("test_type", sa.String(10), nullable=False),
            sa.Column("mock_scores", sa.JSON(), nullable=False),
            sa.Column("target_score", sa.String(20), nullable=True),
            sa.Column("actual_score", sa.String(20), nullable=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_school_test_prep_records_school_student_id", "school_test_prep_records", ["school_student_id"])

    if "school_language_records" not in inspector.get_table_names():
        op.create_table(
            "school_language_records",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("school_student_id", sa.Uuid(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
            sa.Column("academic_team_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("language", sa.String(60), nullable=False),
            sa.Column("level", sa.String(30), nullable=True),
            sa.Column("classes_attended", sa.Integer(), nullable=False),
            sa.Column("assessment_score", sa.String(20), nullable=True),
            sa.Column("certification_status", sa.String(20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_school_language_records_school_student_id", "school_language_records", ["school_student_id"])


def downgrade() -> None:
    op.drop_table("school_language_records")
    op.drop_table("school_test_prep_records")
    op.drop_index("ix_overseas_applications_school_student_id", table_name="overseas_applications")
    op.drop_column("overseas_applications", "school_student_id")
    op.alter_column("overseas_applications", "student_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)
    op.drop_column("school_activities", "activity_type")
    op.drop_column("schools", "tier_valid_until")
    op.drop_column("schools", "tier")
