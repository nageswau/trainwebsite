"""ENH-024 -- Skill India certification details on portfolio_entries.

Revision ID: 0042_skill_india_certification
Revises: 0041_student_master_fields

docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md §4 (DEC-SCOPE-031). Additive only: four nullable
columns and four CHECKs. Every existing row is all-NULL in the new columns, which satisfies every CHECK, so nothing is backfilled
or rewritten. `downgrade()` drops only what this adds (entries survive as plain certifications).
"""

import sqlalchemy as sa

from alembic import op

revision = "0042_skill_india_certification"
down_revision = "0041_student_master_fields"
branch_labels = None
depends_on = None

TABLE = "portfolio_entries"
COLUMNS = (
    ("certification_type", sa.String(30)),
    ("certification_status", sa.String(20)),
    ("certificate_number", sa.String(100)),
    ("issued_on", sa.Date()),
)
# Verbatim copies of PortfolioEntry.__table_args__ (a migration never imports the live models).
CHECKS = (
    ("ck_portfolio_cert_type", "certification_type IS NULL OR (certification_type = 'skill_india' AND section = 'certification')"),
    ("ck_portfolio_cert_status", "certification_status IS NULL OR certification_status IN ('enrolled', 'in_progress', 'certified')"),
    (
        "ck_portfolio_cert_fields",
        "(certification_type IS NULL AND certification_status IS NULL AND certificate_number IS NULL AND issued_on IS NULL) "
        "OR (certification_type IS NOT NULL AND certification_status IS NOT NULL)",
    ),
    ("ck_portfolio_cert_certified", "certification_status IS DISTINCT FROM 'certified' OR (certificate_number IS NOT NULL AND issued_on IS NOT NULL)"),
)


def upgrade() -> None:
    # Guarded: on a fresh database 0001_initial's Base.metadata.create_all() has already built portfolio_entries from the *current*
    # models (columns and CHECKs included) -- same reason 0041 guards.
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns(TABLE)}
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints(TABLE)}
    for name, condition in CHECKS:
        if name not in checks:
            op.create_check_constraint(name, TABLE, condition)


def downgrade() -> None:
    for name, _ in CHECKS:
        op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {name}")
    for name, _ in COLUMNS:
        op.drop_column(TABLE, name)
