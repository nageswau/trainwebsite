"""upc-003 -- Global University Master: code, master fields, ownership, publish flag, rankings, assignment history.

Revision ID: 0105_university_master
Revises: 0104_skills_master

docs/superpowers/specs/2026-10-08-upc-003-university-master-design.md §2 (DEC-SCOPE-120). Extends `universities` in place (U5): every
existing row keeps its slug and content, gets a `UNV-` code in (created_at, slug) order, and stays public (`catalogue_visible` and
`active` default true). 0001 builds a fresh database from the current models, which already carry all of this, so each step is guarded.
CHECKS repeats app.models.UNIVERSITY_CHECKS (test_upc_003_migration). downgrade() refuses while rankings, assignment history, or any
internal (unpublished or inactive) university exist: dropping the flags would publish those rows.

Re-chained 2026-10-08 on merging `main` @ `0ef88a98`: drafted as `0104_university_master` on `0103_partnership_profiles`, but rec-006's
`0104_skills_master` merged first, so this is `0105` after it (DEC-SCOPE-120, API §12AN, RBAC §2.46). A database stamped at
`0104_university_master` is re-stamped with `alembic stamp --purge 0103_partnership_profiles`, then `upgrade head` (every step here is guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0105_university_master"
down_revision = "0104_skills_master"
branch_labels = None
depends_on = None

TABLE = "universities"
SEQ = "university_code_seq"
CODE_DEFAULT = f"'UNV-' || translate(format('%6s', nextval('{SEQ}')), ' ', '0')"
UNIQUE = "uq_universities_code"
INDEXES = {"ix_universities_primary_manager": "primary_manager_user_id", "ix_universities_backup_manager": "backup_manager_user_id", "ix_universities_priority": "priority"}
CHECKS = {
    "ck_universities_institution_type": "institution_type IN ('university', 'college', 'institute', 'language_school', 'training_institution')",
    "ck_universities_ownership_type": "ownership_type IS NULL OR ownership_type IN ('public', 'private')",
    "ck_universities_existing_relationship": "existing_relationship IS NULL OR existing_relationship IN ('new', 'existing')",
    "ck_universities_priority": "priority IS NULL OR priority IN ('A', 'B', 'C')",
    "ck_universities_partnership_potential": "partnership_potential IS NULL OR partnership_potential IN ('high', 'medium', 'low')",
    "ck_universities_backup_needs_primary": "backup_manager_user_id IS NULL OR (primary_manager_user_id IS NOT NULL AND backup_manager_user_id <> primary_manager_user_id)",
}
UUID = postgresql.UUID(as_uuid=True)


def _columns() -> list[sa.Column]:
    """Fresh Column objects per call: a Column binds to one table."""
    return [
        sa.Column("university_code", sa.String(20), nullable=True),  # NOT NULL after the backfill
        sa.Column("institution_type", sa.String(30), nullable=False, server_default=sa.text("'university'")),
        sa.Column("ownership_type", sa.String(10), nullable=True),
        sa.Column("state_region", sa.String(120), nullable=True),
        sa.Column("website", sa.String(300), nullable=True),
        sa.Column("course_levels", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("popular_programs", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("international_office", sa.Text(), nullable=True),
        sa.Column("existing_relationship", sa.String(10), nullable=True),
        sa.Column("primary_manager_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("backup_manager_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("priority", sa.String(1), nullable=True),
        sa.Column("partnership_potential", sa.String(10), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("catalogue_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    ]


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspector()
    op.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}"))
    present = set() if inspector is None else {c["name"] for c in inspector.get_columns(TABLE)}
    for column in _columns():
        if column.name not in present:
            op.add_column(TABLE, column)

    # One statement: nextval runs over the ordered sub-select, so codes follow (created_at, slug).
    op.execute(
        sa.text(
            f"UPDATE {TABLE} u SET university_code = 'UNV-' || translate(format('%6s', o.n), ' ', '0') "
            f"FROM (SELECT id, nextval('{SEQ}') AS n FROM (SELECT id FROM {TABLE} WHERE university_code IS NULL ORDER BY created_at, slug) s) o "
            "WHERE u.id = o.id"
        )
    )
    op.alter_column(TABLE, "university_code", nullable=False, server_default=sa.text(CODE_DEFAULT))

    names = (
        set()
        if inspector is None
        else ({c["name"] for c in inspector.get_unique_constraints(TABLE)} | {c["name"] for c in inspector.get_check_constraints(TABLE)} | {i["name"] for i in inspector.get_indexes(TABLE)})
    )
    if UNIQUE not in names:
        op.create_unique_constraint(UNIQUE, TABLE, ["university_code"])
    for name, sql in CHECKS.items():
        if name not in names:
            op.create_check_constraint(name, TABLE, sql)
    for name, column in INDEXES.items():
        if name not in names:
            op.create_index(name, TABLE, [column])

    tables = set() if inspector is None else set(inspector.get_table_names())
    if "university_rankings" not in tables:
        op.create_table(
            "university_rankings",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("university_id", UUID, sa.ForeignKey("universities.id", ondelete="CASCADE"), nullable=False),
            sa.Column("system", sa.String(10), nullable=False),
            sa.Column("other_name", sa.String(80), nullable=True),
            sa.Column("year", sa.Integer(), nullable=False),
            sa.Column("rank", sa.String(20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("system IN ('QS', 'THE', 'ARWU', 'Other')", name="ck_university_rankings_system"),
            sa.CheckConstraint("(system = 'Other') = (other_name IS NOT NULL)", name="ck_university_rankings_other_name"),
            sa.CheckConstraint("year BETWEEN 1900 AND 2100", name="ck_university_rankings_year"),
        )
        op.create_index("uq_university_rankings_entry", "university_rankings", ["university_id", "system", sa.text("coalesce(other_name, '')"), "year"], unique=True)
    if "university_assignment_history" not in tables:
        op.create_table(
            "university_assignment_history",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("university_id", UUID, sa.ForeignKey("universities.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("slot", sa.String(10), nullable=False),
            sa.Column("from_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("to_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("slot IN ('primary', 'backup')", name="ck_university_assignment_history_slot"),
        )
        op.create_index("ix_university_assignment_history_university", "university_assignment_history", ["university_id"])


def downgrade() -> None:
    if not op.get_context().as_sql:
        found = (
            op.get_bind()
            .execute(
                sa.text(f"SELECT 1 FROM university_rankings UNION ALL SELECT 1 FROM university_assignment_history UNION ALL SELECT 1 FROM {TABLE} WHERE NOT catalogue_visible OR NOT active LIMIT 1")
            )
            .first()
        )
        if found:
            raise RuntimeError("Cannot downgrade 0105_university_master: rankings, assignment history or internal universities exist. Remove or publish them deliberately first.")
    op.drop_table("university_assignment_history")
    op.drop_table("university_rankings")
    for name in INDEXES:
        op.drop_index(name, table_name=TABLE)
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    for column in reversed(_columns()):
        op.drop_column(TABLE, column.name)
    op.execute(sa.text(f"DROP SEQUENCE IF EXISTS {SEQ}"))
