"""upc-004 -- duplicate key on universities + the BDM University organization's link to the master.

Revision ID: 0106_university_duplicates
Revises: 0105_university_master

docs/superpowers/specs/2026-10-08-upc-004-university-duplicates-design.md §2 (DEC-SCOPE-121). `universities.name_key` is backfilled in
Python with the model's own normalize_key, then made NOT NULL and indexed with the country (not unique: an override may keep two rows).
`bdm_organizations.university_id` is a nullable FK, University organizations only (CHECK). Existing duplicates are only reported (UD12):
the duplicate groups in the master and the unlinked BDM University organizations whose name matches it are logged, never merged or
linked. 0001 builds a fresh database from the current models, which already carry all of this, so each step is guarded. downgrade()
refuses while any BDM organization is linked: dropping the column would lose the link.
"""

import logging

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.identifiers import normalize_key

revision = "0106_university_duplicates"
down_revision = "0105_university_master"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

KEY_LENGTH = 200
KEY_INDEX = "ix_universities_duplicate_key"
LINK_INDEX = "ix_bdm_organizations_university"
LINK_CHECK = "ck_bdm_organizations_university_link"
LINK_SQL = "university_id IS NULL OR org_type = 'university'"  # = app.models.BDM_UNIVERSITY_LINK_SQL (test_upc_004_migration)
LINK_FK = "fk_bdm_organizations_university_id"


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def _backfill(bind) -> None:
    rows = bind.execute(sa.text("SELECT id, name FROM universities WHERE name_key IS NULL")).fetchall()
    for uni_id, name in rows:
        bind.execute(sa.text("UPDATE universities SET name_key = :k WHERE id = :id"), {"k": normalize_key(name, KEY_LENGTH), "id": uni_id})


def _report(bind) -> None:
    groups = bind.execute(sa.text("SELECT count(*) FROM (SELECT 1 FROM universities GROUP BY country_id, name_key HAVING count(*) > 1) g")).scalar()
    candidates = bind.execute(
        sa.text("SELECT count(*) FROM bdm_organizations o WHERE o.org_type = 'university' AND o.university_id IS NULL AND EXISTS (SELECT 1 FROM universities u WHERE u.name_key = o.name_key)")
    ).scalar()
    logger.warning(
        "upc-004 report: %s duplicate group(s) in universities (same country + name); %s unlinked BDM University organization(s) match a master name. Nothing was merged or linked.", groups, candidates
    )


def upgrade() -> None:
    inspector = _inspector()
    uni_cols = set() if inspector is None else {c["name"] for c in inspector.get_columns("universities")}
    if "name_key" not in uni_cols:
        op.add_column("universities", sa.Column("name_key", sa.String(KEY_LENGTH), nullable=True))
    if inspector is not None:
        _backfill(op.get_bind())
    op.alter_column("universities", "name_key", nullable=False)
    if inspector is None or KEY_INDEX not in {i["name"] for i in inspector.get_indexes("universities")}:
        op.create_index(KEY_INDEX, "universities", ["country_id", "name_key"])

    org_cols = set() if inspector is None else {c["name"] for c in inspector.get_columns("bdm_organizations")}
    if "university_id" not in org_cols:
        op.add_column("bdm_organizations", sa.Column("university_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(LINK_FK, "bdm_organizations", "universities", ["university_id"], ["id"], ondelete="RESTRICT")
    names = set() if inspector is None else {i["name"] for i in inspector.get_indexes("bdm_organizations")} | {c["name"] for c in inspector.get_check_constraints("bdm_organizations")}
    if LINK_INDEX not in names:
        op.create_index(LINK_INDEX, "bdm_organizations", ["university_id"])
    if LINK_CHECK not in names:
        op.create_check_constraint(LINK_CHECK, "bdm_organizations", LINK_SQL)
    if inspector is not None:
        _report(op.get_bind())


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM bdm_organizations WHERE university_id IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0106_university_duplicates: BDM organizations are linked to the University Master. Unlink them deliberately first.")
    op.drop_constraint(LINK_CHECK, "bdm_organizations", type_="check")
    op.drop_index(LINK_INDEX, table_name="bdm_organizations")
    op.drop_column("bdm_organizations", "university_id")  # drops whichever FK constraint carries it (0001-built or LINK_FK)
    op.drop_index(KEY_INDEX, table_name="universities")
    op.drop_column("universities", "name_key")
