"""pob-014 -- institution-supplied student pool with permission tracking (DEC-SCOPE-425 S1-S7).

Revision ID: 0306_institution_student_pool
Revises: 0305_po_targets_reports

docs/superpowers/specs/2026-11-07-pob-014-institution-student-pool-design.md. Additive only: two new tables, three nullable columns on
`candidates` and one on `candidate_import_batches`; no existing row changes. 0001 runs `create_all` from today's models, so a fresh
database already has everything: each step runs only when missing. PERMISSION_CHECKS and CANDIDATE_CHECKS are frozen copies of
`models.INSTITUTION_PERMISSION_CHECKS` and `models.CANDIDATE_INSTITUTION_CHECKS`. The downgrade drops what the upgrade added.
"""

import sqlalchemy as sa

from alembic import op

revision = "0306_institution_student_pool"
down_revision = "0305_po_targets_reports"
branch_labels = None
depends_on = None

PERMISSION_CHECKS = {"ck_institution_data_permissions_window": "expires_on >= valid_from"}
CANDIDATE_CHECKS = {
    "ck_candidates_institution_notice": "institution_notice_status IS NULL OR institution_notice_status IN ('notice_sent', 'consented')",
    "ck_candidates_institution_pair": "(institution_permission_id IS NULL) = (institution_org_id IS NULL)",
}
PERMISSIONS = "institution_data_permissions"
PERMISSION_USERS = "institution_data_permission_users"


def _user(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def _existing() -> tuple[set, set, set, set, set]:
    if op.get_context().as_sql:
        return set(), set(), set(), set(), set()
    inspector = sa.inspect(op.get_bind())
    return (
        set(inspector.get_table_names()),
        {c["name"] for c in inspector.get_columns("candidates")},
        {c["name"] for c in inspector.get_check_constraints("candidates")},
        {i["name"] for i in inspector.get_indexes("candidates")},
        {c["name"] for c in inspector.get_columns("candidate_import_batches")},
    )


def upgrade() -> None:
    tables, columns, checks, indexes, batch_columns = _existing()
    if PERMISSIONS not in tables:
        op.create_table(
            PERMISSIONS,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("mou_id", sa.Uuid(), sa.ForeignKey("bdm_mous.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("agreement_reference", sa.String(100), nullable=False),
            sa.Column("purposes", sa.JSON(), nullable=False),
            sa.Column("valid_from", sa.Date(), nullable=False),
            sa.Column("expires_on", sa.Date(), nullable=False),
            sa.Column("notes", sa.String(500), nullable=True),
            _user("created_by_user_id"),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            _user("revoked_by_user_id", nullable=True),
            *(sa.Column(n, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False) for n in ("created_at", "updated_at")),
            *(sa.CheckConstraint(sql, name=name) for name, sql in PERMISSION_CHECKS.items()),
        )
        op.create_index("ix_institution_data_permissions_org", PERMISSIONS, ["organization_id", "created_at"])
    if PERMISSION_USERS not in tables:
        op.create_table(
            PERMISSION_USERS,
            sa.Column("permission_id", sa.Uuid(), sa.ForeignKey(f"{PERMISSIONS}.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
            _user("added_by_user_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_institution_data_permission_users_user", PERMISSION_USERS, ["user_id"])
    if "institution_org_id" not in columns:
        op.add_column("candidates", sa.Column("institution_org_id", sa.Uuid(), sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=True))
    if "institution_permission_id" not in columns:
        op.add_column("candidates", sa.Column("institution_permission_id", sa.Uuid(), sa.ForeignKey(f"{PERMISSIONS}.id", ondelete="RESTRICT"), nullable=True))
    if "institution_notice_status" not in columns:
        op.add_column("candidates", sa.Column("institution_notice_status", sa.String(12), nullable=True))
    for name, sql in CANDIDATE_CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "candidates", sql)
    if "ix_candidates_institution_org_id" not in indexes:
        op.create_index("ix_candidates_institution_org_id", "candidates", ["institution_org_id"])
    if "ix_candidates_institution_permission" not in indexes:
        op.create_index("ix_candidates_institution_permission", "candidates", ["institution_permission_id"], postgresql_where=sa.text("institution_permission_id IS NOT NULL"))
    if "institution_permission_id" not in batch_columns:
        op.add_column("candidate_import_batches", sa.Column("institution_permission_id", sa.Uuid(), sa.ForeignKey(f"{PERMISSIONS}.id", ondelete="RESTRICT"), nullable=True))


def downgrade() -> None:
    op.drop_column("candidate_import_batches", "institution_permission_id")
    op.drop_index("ix_candidates_institution_permission", table_name="candidates")
    op.drop_index("ix_candidates_institution_org_id", table_name="candidates")
    for name in CANDIDATE_CHECKS:
        op.drop_constraint(name, "candidates", type_="check")
    for column in ("institution_notice_status", "institution_permission_id", "institution_org_id"):
        op.drop_column("candidates", column)
    op.drop_table(PERMISSION_USERS)
    op.drop_table(PERMISSIONS)
