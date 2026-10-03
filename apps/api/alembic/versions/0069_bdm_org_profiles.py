"""bdm-003 -- type-specific organization profiles: twelve nullable columns and nine CHECKs on bdm_organizations.

Revision ID: 0069_bdm_org_profiles
Revises: 0068_bdm_trips

docs/superpowers/specs/2026-10-03-bdm-003-type-specific-profiles-design.md §4 (DEC-SCOPE-064). No row is read or written by upgrade():
every existing row has NULL in every new column, which satisfies every CHECK. 0001 builds a fresh database from the current models (which
already carry the columns and CHECKs), so each column and CHECK is added only when missing. downgrade() refuses while any profile value
exists: entered data is never dropped silently. CHECKS must equal app.models.BDM_PROFILE_CHECKS (test_bdm_003_migration).

Re-chained 2026-10-03 on merging `main`: cut as `0068_bdm_org_profiles` after `0067_audit_entity_index`, but bdm-010's
`0068_bdm_trips` reached `main` first, so this revision is now `0069_bdm_org_profiles` after 0068_bdm_trips (one head). A database
stamped at `0068_bdm_org_profiles` is re-stamped with `alembic stamp --purge 0067_audit_entity_index` then `upgrade head` (every
create here is guarded, so the re-run is harmless).
"""

import sqlalchemy as sa

from alembic import op

revision = "0069_bdm_org_profiles"
down_revision = "0068_bdm_trips"
branch_labels = None
depends_on = None

TABLE = "bdm_organizations"
COLUMNS = (
    ("address", sa.String(500)),
    ("country", sa.String(120)),
    ("territory", sa.String(120)),
    ("source", sa.String(20)),
    ("staff_count", sa.Integer()),
    ("board", sa.String(10)),
    ("school_type", sa.String(20)),
    ("grade_from", sa.SmallInteger()),
    ("grade_to", sa.SmallInteger()),
    ("affiliation", sa.String(200)),
    ("college_type", sa.String(20)),
    ("courses", sa.String(1000)),
)
CHECKS = {
    "ck_bdm_organizations_source": "source IS NULL OR source IN ('referral', 'website', 'event', 'cold_call', 'walk_in', 'other')",
    "ck_bdm_organizations_staff_count": "staff_count IS NULL OR staff_count BETWEEN 0 AND 100000",
    "ck_bdm_organizations_board": "board IS NULL OR board IN ('CBSE', 'ICSE', 'State', 'IB', 'Other')",
    "ck_bdm_organizations_school_type": "school_type IS NULL OR school_type IN ('private', 'government', 'aided', 'international', 'other')",
    "ck_bdm_organizations_grades": "(grade_from IS NULL OR grade_from BETWEEN -2 AND 12) AND (grade_to IS NULL OR grade_to BETWEEN -2 AND 12) AND (grade_from IS NULL OR grade_to IS NULL OR grade_from <= grade_to)",
    "ck_bdm_organizations_college_type": "college_type IS NULL OR college_type IN ('engineering', 'arts_science', 'management', 'medical', 'polytechnic', 'other')",
    "ck_bdm_organizations_agent_profile": "org_type IN ('agent') OR (country IS NULL AND territory IS NULL AND source IS NULL AND staff_count IS NULL)",
    "ck_bdm_organizations_school_profile": "org_type IN ('school') OR (board IS NULL AND school_type IS NULL AND grade_from IS NULL AND grade_to IS NULL)",
    "ck_bdm_organizations_college_profile": "org_type IN ('college', 'university') OR (affiliation IS NULL AND college_type IS NULL AND courses IS NULL)",
}


def _present() -> tuple[set[str], set[str]]:
    if op.get_context().as_sql:  # offline SQL: emit everything
        return set(), set()
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(TABLE)}, {c["name"] for c in inspector.get_check_constraints(TABLE)}


def upgrade() -> None:
    columns, checks = _present()
    for name, type_ in COLUMNS:
        if name not in columns:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)


def downgrade() -> None:
    if not op.get_context().as_sql:
        filled = " OR ".join(f"{name} IS NOT NULL" for name, _ in COLUMNS)
        if op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} WHERE {filled} LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0069_bdm_org_profiles: organization profile values exist. Clear them deliberately first.")
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    for name, _ in reversed(COLUMNS):
        op.drop_column(TABLE, name)
