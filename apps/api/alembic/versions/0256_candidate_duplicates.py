"""hrc-014 -- candidate duplicate review and merge: `candidates.merged_*`, the `candidate_duplicates` review queue, and the default
`candidates.merge` grant (placement managers).

Revision ID: 0256_candidate_duplicates
Revises: 0255_candidate_documents

docs/superpowers/specs/2026-11-04-hrc-014-candidate-duplicate-merge-design.md (DEC-SCOPE-377). Nullable columns and one new table; 0001
builds a fresh database from the current models, which already carry them, so each step runs only when missing (0251's idiom). No backfill:
existing pairs are found by the queue's "Check the whole pool" scan. The checks and SEED are frozen copies of the model / `rbac` at this
revision. The downgrade drops the table, the columns and the `candidates.merge` grant rows (with their overrides); no candidate data changes.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0256_candidate_duplicates"
down_revision = "0255_candidate_documents"
branch_labels = None
depends_on = None

MERGE_CHECKS = {
    "ck_candidates_merged": "(merged_into_id IS NULL) = (merged_at IS NULL) AND (merged_at IS NULL) = (merged_by_user_id IS NULL) AND (merged_into_id IS NULL OR archived_at IS NOT NULL)",
    "ck_candidates_merged_self": "merged_into_id IS NULL OR merged_into_id <> id",
}
DUPLICATE_CHECKS = {
    "ck_candidate_duplicates_order": "candidate_id < other_id",
    "ck_candidate_duplicates_status": "status IN ('open', 'dismissed', 'merged')",
    "ck_candidate_duplicates_decided": "(status = 'open') = (decided_at IS NULL)",
    "ck_candidate_duplicates_note": "note IS NULL OR char_length(note) <= 500",
}
SEED = (("placement_manager", "candidates", "merge"),)
FK = "fk_candidates_merged_into_id"


def _columns() -> list[sa.Column]:
    return [
        sa.Column("merged_into_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
    ]


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns("candidates")}
    for column in _columns():
        if column.name not in existing:
            op.add_column("candidates", column)
    if "merged_into_id" not in existing:
        op.create_foreign_key(FK, "candidates", "candidates", ["merged_into_id"], ["id"], ondelete="RESTRICT")
    checks = set() if offline else {c["name"] for c in inspector.get_check_constraints("candidates")}
    for name, sql in MERGE_CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "candidates", sql)
    if offline or "candidate_duplicates" not in set(inspector.get_table_names()):
        op.create_table(
            "candidate_duplicates",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("other_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("signals", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(10), server_default=sa.text("'open'"), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("candidate_id", "other_id", name="uq_candidate_duplicates_pair"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in DUPLICATE_CHECKS.items()),
        )
        op.create_index("ix_candidate_duplicates_status", "candidate_duplicates", ["status", "created_at"])
        op.create_index("ix_candidate_duplicates_other", "candidate_duplicates", ["other_id"])
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    # only `merge`: hrc-002 declared the same resource's export/import keys, which other items own
    op.execute("DELETE FROM user_permission_overrides WHERE resource = 'candidates' AND action = 'merge'")
    op.execute("DELETE FROM role_permissions WHERE resource = 'candidates' AND action = 'merge'")
    op.drop_table("candidate_duplicates")
    for name in MERGE_CHECKS:
        op.drop_constraint(name, "candidates", type_="check")
    for column in reversed(_columns()):  # the self-reference goes with its column, whatever 0001 or this revision named it
        op.drop_column("candidates", column.name)
