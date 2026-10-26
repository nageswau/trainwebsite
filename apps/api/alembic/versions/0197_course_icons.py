"""nehn-036 -- an optional subject icon per overseas course.

Revision ID: 0197_course_icons
Revises: 0196_role_permissions

docs/superpowers/specs/2026-10-26-nehn-036-course-icons-design.md (DEC-SCOPE-285 I3). Adds `overseas_courses.icon` (varchar(20), nullable,
one of the curated keys) and its CHECK only when missing (0001 builds a fresh database from the current models; 0195's idiom). Existing
courses keep NULL, which the web client shows as the icon derived from the category. The downgrade drops the column (and its CHECK).
"""

import sqlalchemy as sa

from alembic import op

revision = "0197_course_icons"
down_revision = "0196_role_permissions"
branch_labels = None
depends_on = None

ICONS = ("ai", "security", "data", "computing", "engineering", "business", "health", "hospitality", "law", "education", "arts", "science", "general")
CHECK = "ck_overseas_courses_icon"
CHECK_SQL = f"icon IS NULL OR icon IN ({', '.join(repr(v) for v in ICONS)})"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "icon" not in {c["name"] for c in inspector.get_columns("overseas_courses")}:
        op.add_column("overseas_courses", sa.Column("icon", sa.String(20), nullable=True))
    if CHECK not in {c["name"] for c in inspector.get_check_constraints("overseas_courses")}:
        op.create_check_constraint(CHECK, "overseas_courses", CHECK_SQL)


def downgrade() -> None:
    op.drop_column("overseas_courses", "icon")  # drops its CHECK with it
