"""itc-026 -- student resume versions and the IT Admin's resume size limit.

Revision ID: 0235_student_resumes
Revises: 0234_it_student_notes

docs/superpowers/specs/2026-11-02-itc-026-student-resumes-design.md (DEC-SCOPE-350). Two new tables; nothing existing changes
(`profile_documents` stays as it is). 0001 builds a fresh database from the current models, which already carry them, so the upgrade is
guarded (0222's idiom). The downgrade refuses while a resume exists: dropping the rows would orphan the stored files.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0235_student_resumes"
down_revision = "0234_it_student_notes"
branch_labels = None
depends_on = None

RESUMES, SETTINGS = "student_resumes", "student_resume_settings"
CEILING = 10 * 1024 * 1024  # models.STUDENT_RESUME_MAX_BYTES_CEILING, frozen here


def upgrade() -> None:
    if not op.get_context().as_sql and RESUMES in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        RESUMES,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("visibility", sa.String(10), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_user_id", "version", name="uq_student_resumes_version"),
        sa.CheckConstraint("visibility IN ('hr', 'private')", name="ck_student_resumes_visibility"),
        sa.CheckConstraint("version >= 1", name="ck_student_resumes_version"),
    )
    op.create_table(
        SETTINGS,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("max_bytes", sa.Integer, nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_student_resume_settings_one_row"),
        sa.CheckConstraint(f"max_bytes BETWEEN 1048576 AND {CEILING}", name="ck_student_resume_settings_max_bytes"),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {RESUMES} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0235: student resumes exist (itc-026)")
    op.drop_table(SETTINGS)
    op.drop_table(RESUMES)
