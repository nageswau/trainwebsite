"""hrc-010 -- candidate profile completion: education, employment and certification rows, structured location, contact preference,
skills extras and preferences.

Revision ID: 0258_candidate_profile
Revises: 0257_job_approval

docs/superpowers/specs/2026-11-04-hrc-010-candidate-profile-design.md (DEC-SCOPE-381). Nullable or defaulted columns and three new
tables; 0001 builds a fresh database from the current models, which already carry them, so each step runs only when missing (0251's
idiom). Backfill (P11): a candidate with a qualification, college or passing year gets education row 1 from them, and a preferred role
becomes `preferred_roles`; `current_company` is not turned into a dateless job. The CHECKS are frozen copies of the model's strings at
this revision. The downgrade drops what this adds; the legacy columns are untouched.
"""

import sqlalchemy as sa

from alembic import op

revision = "0258_candidate_profile"
down_revision = "0257_job_approval"
branch_labels = None
depends_on = None

TYPES = "'full_time', 'part_time', 'contract', 'internship', 'temporary'"
CHECKS = {
    "ck_candidates_preferred_contact": "preferred_contact IS NULL OR preferred_contact IN ('phone', 'whatsapp', 'email')",
    "ck_candidates_relevant_experience": "relevant_experience_months IS NULL OR relevant_experience_months BETWEEN 0 AND 600",
}
EMPLOYMENT_CHECKS = {
    "ck_candidate_employment_dates": "end_date IS NULL OR end_date >= start_date",
    "ck_candidate_employment_type": f"employment_type IS NULL OR employment_type IN ({TYPES})",
}
CERTIFICATION_CHECKS = {"ck_candidate_certifications_dates": "expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on"}
LISTS = ("tools", "languages", "preferred_roles", "work_modes", "employment_types", "shifts")


def _columns() -> list[sa.Column]:
    return [
        sa.Column("country", sa.String(80), nullable=True),
        sa.Column("state", sa.String(80), nullable=True),
        sa.Column("city", sa.String(80), nullable=True),
        sa.Column("preferred_contact", sa.String(10), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("relevant_experience_months", sa.Integer(), nullable=True),
        *(sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text("'[]'")) for name in LISTS),
        sa.Column("available_from", sa.Date(), nullable=True),
        sa.Column("willing_to_relocate", sa.Boolean(), nullable=True),
    ]


def _row(name: str, checks: dict[str, str], *columns: sa.Column) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        *columns,
        *(sa.CheckConstraint(sql, name=check) for check, sql in checks.items()),
    )
    op.create_index(f"ix_{name}_candidate", name, ["candidate_id", "position"])


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns("candidates")}
    for column in _columns():
        if column.name not in existing:
            op.add_column("candidates", column)
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints("candidates")}
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "candidates", sql)
    if offline or "is_primary" not in {c["name"] for c in inspector.get_columns("candidate_skills")}:
        op.add_column("candidate_skills", sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    tables = set() if offline else set(inspector.get_table_names())
    if "candidate_education" not in tables:
        _row(
            "candidate_education",
            {"ck_candidate_education_year": "year IS NULL OR year BETWEEN 1950 AND 2100"},
            sa.Column("degree", sa.String(120), nullable=True),
            sa.Column("specialisation", sa.String(120), nullable=True),
            sa.Column("institution", sa.String(200), nullable=True),
            sa.Column("year", sa.SmallInteger(), nullable=True),
            sa.Column("grade", sa.String(20), nullable=True),
        )
        # P11: the legacy single fields become education row 1.
        op.execute(
            "INSERT INTO candidate_education (id, candidate_id, position, degree, institution, year) "
            "SELECT gen_random_uuid(), id, 1, qualification, college, passing_year FROM candidates "
            "WHERE qualification IS NOT NULL OR college IS NOT NULL OR passing_year IS NOT NULL"
        )
    if "candidate_employment" not in tables:
        _row(
            "candidate_employment",
            EMPLOYMENT_CHECKS,
            sa.Column("employer", sa.String(200), nullable=False),
            sa.Column("designation", sa.String(120), nullable=True),
            sa.Column("industry", sa.String(120), nullable=True),
            sa.Column("employment_type", sa.String(16), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=True),
        )
    if "candidate_certifications" not in tables:
        _row(
            "candidate_certifications",
            CERTIFICATION_CHECKS,
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("issuer", sa.String(200), nullable=True),
            sa.Column("issued_on", sa.Date(), nullable=True),
            sa.Column("expires_on", sa.Date(), nullable=True),
            sa.Column("credential_id", sa.String(100), nullable=True),
        )
    op.execute("UPDATE candidates SET preferred_roles = json_build_array(preferred_role) WHERE preferred_role IS NOT NULL AND preferred_roles::text = '[]'")


def downgrade() -> None:
    for table in ("candidate_certifications", "candidate_employment", "candidate_education"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("ALTER TABLE candidate_skills DROP COLUMN IF EXISTS is_primary")
    for name in CHECKS:
        op.execute(f"ALTER TABLE candidates DROP CONSTRAINT IF EXISTS {name}")
    for column in _columns():
        op.execute(f"ALTER TABLE candidates DROP COLUMN IF EXISTS {column.name}")
