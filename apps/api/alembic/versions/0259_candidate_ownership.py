"""hrc-012 -- candidate ownership: `candidates.owner_user_id` / `placement_officer_user_id`, `candidate_collaborators`,
`candidate_assignment_history` and the one-row `candidate_ownership_settings`.

Revision ID: 0259_candidate_ownership
Revises: 0258_vacancy_fields

docs/superpowers/specs/2026-11-04-hrc-012-candidate-ownership-design.md (DEC-SCOPE-382). Nullable columns and three new tables; 0001 builds
a fresh database from the current models, which already carry them, so each step runs only when missing (0251's idiom). Backfill (O9):
when the owner column is added, a candidate created by a recruiter (`placement_team`) is owned by them; every other row stays unassigned.
No history rows are invented. The checks are frozen copies of the models at this revision. The downgrade drops the tables and columns.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0259_candidate_ownership"
down_revision = "0258_vacancy_fields"
branch_labels = None
depends_on = None

HISTORY_CHECKS = {
    "ck_candidate_assignment_history_kind": "kind IN ('owner', 'placement_officer', 'collaborator_added', 'collaborator_removed')",
    "ck_candidate_assignment_history_reason": "reason IN ('create', 'assign', 'reassign')",
}
COLUMNS = ("owner_user_id", "placement_officer_user_id")
BACKFILL = "UPDATE candidates SET owner_user_id = created_by_user_id FROM users WHERE users.id = candidates.created_by_user_id AND users.role = 'placement_team'"


def _uuid(name: str, *, fk: str | None = "users.id", nullable: bool = False, ondelete: str | None = None) -> sa.Column:
    args = [sa.ForeignKey(fk, ondelete=ondelete)] if fk else []
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, nullable=nullable)


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    existing = set() if offline else {c["name"] for c in inspector.get_columns("candidates")}
    for name in COLUMNS:
        if name not in existing:
            op.add_column("candidates", _uuid(name, nullable=True))
            op.create_index(f"ix_candidates_{name}", "candidates", [name])
    if "owner_user_id" not in existing:
        op.execute(BACKFILL)
    tables = set() if offline else set(inspector.get_table_names())
    if "candidate_collaborators" not in tables:
        op.create_table(
            "candidate_collaborators",
            _uuid("id", fk=None),
            _uuid("candidate_id", fk="candidates.id", ondelete="CASCADE"),
            _uuid("user_id"),
            _uuid("added_by_user_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("candidate_id", "user_id", name="uq_candidate_collaborators_pair"),
        )
        op.create_index("ix_candidate_collaborators_user", "candidate_collaborators", ["user_id"])
    if "candidate_assignment_history" not in tables:
        op.create_table(
            "candidate_assignment_history",
            _uuid("id", fk=None),
            _uuid("candidate_id", fk="candidates.id", ondelete="CASCADE"),
            sa.Column("kind", sa.String(24), nullable=False),
            _uuid("from_user_id", nullable=True),
            _uuid("to_user_id", nullable=True),
            _uuid("changed_by_user_id"),
            sa.Column("reason", sa.String(10), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            *(sa.CheckConstraint(sql, name=name) for name, sql in HISTORY_CHECKS.items()),
        )
        op.create_index("ix_candidate_assignment_history_candidate", "candidate_assignment_history", ["candidate_id", "created_at"])
    if "candidate_ownership_settings" not in tables:
        op.create_table(
            "candidate_ownership_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("shared_ownership", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            _uuid("updated_by_user_id", nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint("id = 1", name="ck_candidate_ownership_settings_one_row"),
        )


def downgrade() -> None:
    for table in ("candidate_ownership_settings", "candidate_assignment_history", "candidate_collaborators"):
        op.drop_table(table)
    for name in COLUMNS:
        op.drop_index(f"ix_candidates_{name}", table_name="candidates")
        op.drop_column("candidates", name)
