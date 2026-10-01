"""AGN-007 -- agency universities and a student's university shortlist (DEC-SCOPE-049).

Revision ID: 0056_agent_shortlist
Revises: 0054_school_onboarding_bulk

docs/superpowers/specs/2026-10-01-agn-007-student-shortlist-design.md §4. Creates two tables only; no existing table or row changes.
0001/0003 run Base.metadata.create_all from the CURRENT models, so a database built from scratch already has both tables when this
runs: each table is created only when missing. downgrade() drops the two new tables (entries first) -- it touches nothing else.
"""

import sqlalchemy as sa

from alembic import op

revision = "0056_agent_shortlist"
down_revision = "0054_school_onboarding_bulk"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    if op.get_context().as_sql:
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    existing = _tables()
    if "agent_universities" not in existing:
        op.create_table(
            "agent_universities",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("org_id", sa.Uuid(), sa.ForeignKey("agent_orgs.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("country", sa.String(120), nullable=False),
            sa.Column("city", sa.String(120), nullable=True),
            sa.Column("entry_requirements", sa.Text(), nullable=True),
            *_audit_columns(),
        )
        op.create_index("ix_agent_universities_org_id", "agent_universities", ["org_id"])
        op.create_index("uq_agent_universities_org_name_country", "agent_universities", ["org_id", sa.text("lower(name)"), sa.text("lower(country)")], unique=True)
    if "agent_student_shortlist_entries" not in existing:
        op.create_table(
            "agent_student_shortlist_entries",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("agent_student_id", sa.Uuid(), sa.ForeignKey("agent_students.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("university_id", sa.Uuid(), sa.ForeignKey("universities.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("agent_university_id", sa.Uuid(), sa.ForeignKey("agent_universities.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("course_id", sa.Uuid(), sa.ForeignKey("overseas_courses.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("course_title", sa.String(200), nullable=True),
            sa.Column("intake", sa.String(120), nullable=True),
            sa.Column("tuition_fee", sa.String(120), nullable=True),
            sa.Column("entry_requirements", sa.Text(), nullable=True),
            *_audit_columns(),
            sa.CheckConstraint("(university_id IS NULL) <> (agent_university_id IS NULL)", name="ck_shortlist_one_university"),
            sa.CheckConstraint("course_id IS NULL OR university_id IS NOT NULL", name="ck_shortlist_catalogue_course"),
            sa.CheckConstraint("course_id IS NULL OR course_title IS NULL", name="ck_shortlist_one_course_form"),
        )
        op.create_index("ix_shortlist_student_created", "agent_student_shortlist_entries", ["agent_student_id", "created_at", "id"])
        op.create_index("ix_agent_student_shortlist_entries_agent_university_id", "agent_student_shortlist_entries", ["agent_university_id"])


def downgrade() -> None:
    op.drop_table("agent_student_shortlist_entries")
    op.drop_table("agent_universities")
