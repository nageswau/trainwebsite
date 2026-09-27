"""ENH-026 -- structured Counselling Record fields on school_career_records.

Revision ID: 0042_career_record_fields
Revises: 0041_student_master_fields

docs/superpowers/specs/2026-09-27-enh-021-026-internship-and-counselling-record-design.md §4.1 (DEC-SCOPE-031).
Additive only: nullable columns, a CHECK on status, one index. No backfill -- existing rows keep status NULL, which
the application treats as "recorded before tracking" (C4/C5). `downgrade()` drops exactly what this adds.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0042_career_record_fields"
down_revision = "0041_student_master_fields"
branch_labels = None
depends_on = None

TABLE = "school_career_records"
JSON = postgresql.JSON(none_as_null=True)
COLUMNS = (
    ("status", sa.String(30)), ("scheduled_for", sa.DateTime(timezone=True)), ("completed_on", sa.Date()),
    ("next_follow_up_date", sa.Date()), ("career_interests", JSON), ("global_education_interest", sa.Boolean()),
    ("academic_strengths", JSON), ("weak_areas", JSON), ("recommended_careers", JSON), ("recommended_courses", JSON),
    ("recommended_stream", JSON), ("recommended_skills", JSON), ("parent_participated", sa.Boolean()),
    ("parent_participation_note", sa.String(500)),
)
STATUS_CHECK = "status IS NULL OR status IN ('not_started', 'scheduled', 'completed', 'follow_up_required')"
INDEX = "ix_school_career_records_student_type_status"


def upgrade() -> None:
    # Guarded like 0041: 0001_initial builds tables from the *current* models, so on a from-scratch replay these exist.
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    if "updated_by_user_id" not in existing:
        op.add_column(TABLE, sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", name="fk_school_career_records_updated_by"), nullable=True))
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints(TABLE)}
    if "ck_career_record_status" not in checks:
        op.create_check_constraint("ck_career_record_status", TABLE, STATUS_CHECK)
    indexes = set() if offline else {i["name"] for i in inspector.get_indexes(TABLE)}
    if INDEX not in indexes:
        op.create_index(INDEX, TABLE, ["school_student_id", "record_type", "status"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_constraint("ck_career_record_status", TABLE, type_="check")
    op.drop_column(TABLE, "updated_by_user_id")
    for name, _type in reversed(COLUMNS):
        op.drop_column(TABLE, name)
