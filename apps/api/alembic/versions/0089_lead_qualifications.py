"""tel-009 -- `lead_qualifications`: a lead's qualification answers (EVID-019 §4).

Revision ID: 0089_lead_qualifications
Revises: 0088_bdm_appointment_trip

docs/superpowers/specs/2026-10-06-tel-009-qualification-form-design.md §2 (DEC-SCOPE-093). One row per lead; the shared answers stay on
`enquiries` (QD1), so no existing column or row changes. 0001 builds a fresh database from the current models, which already carry the
table, so the upgrade is guarded (0074's idiom).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0089_lead_qualifications"
down_revision = "0088_bdm_appointment_trip"
branch_labels = None
depends_on = None

TABLE = "lead_qualifications"
# Frozen copies of the model's CHECKs; test_tel_009_migration asserts they stay identical.
CHECKS = {
    "ck_lead_qualifications_experience": "work_experience_years IS NULL OR work_experience_years BETWEEN 0 AND 50",
    "ck_lead_qualifications_percentage": "academic_percentage IS NULL OR academic_percentage BETWEEN 0 AND 100",
    "ck_lead_qualifications_skill_level": "it_skill_level IS NULL OR it_skill_level IN ('beginner', 'intermediate', 'advanced')",
    "ck_lead_qualifications_mode": "preferred_mode IS NULL OR preferred_mode IN ('online', 'offline')",
    "ck_lead_qualifications_study_level": "study_level IS NULL OR study_level IN ('ug', 'masters')",
    "ck_lead_qualifications_passport": "passport_status IS NULL OR passport_status IN ('none', 'applied', 'valid')",
}


def upgrade() -> None:
    if not op.get_context().as_sql and sa.inspect(op.get_bind()).has_table(TABLE):
        return
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("lead_id", uuid, sa.ForeignKey("enquiries.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("current_org", sa.String(200), nullable=True),
        sa.Column("work_experience_years", sa.SmallInteger(), nullable=True),
        sa.Column("it_skill_level", sa.String(20), nullable=True),
        sa.Column("career_objective", sa.String(500), nullable=True),
        sa.Column("preferred_batch", sa.String(120), nullable=True),
        sa.Column("budget_range", sa.String(120), nullable=True),
        sa.Column("preferred_mode", sa.String(10), nullable=True),
        sa.Column("study_level", sa.String(10), nullable=True),
        sa.Column("preferred_course", sa.String(200), nullable=True),
        sa.Column("intake", sa.String(40), nullable=True),
        sa.Column("academic_percentage", sa.Numeric(5, 2), nullable=True),
        sa.Column("english_test_status", sa.String(120), nullable=True),
        sa.Column("passport_status", sa.String(10), nullable=True),
        sa.Column("updated_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
