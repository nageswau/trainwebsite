"""hrc-020 -- saved Find Candidates searches and the default `candidates.export` grant (placement managers).

Revision ID: 0277_saved_candidate_searches
Revises: 0276_interview_completion

docs/superpowers/specs/2026-11-05-hrc-020-saved-searches-export-design.md (DEC-SCOPE-401 X1, X12). One new table; 0001 builds a fresh
database from the current models, which already carry it, so it is created only when missing (0256's idiom). The check and SEED are
frozen copies of the model / `rbac` at this revision. The downgrade drops the table and the `candidates.export` grant rows (with their
overrides); no candidate changes.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0277_saved_candidate_searches"
down_revision = "0276_interview_completion"
branch_labels = None
depends_on = None

CHECKS = {"ck_saved_candidate_searches_name": "char_length(name) BETWEEN 1 AND 80"}
SEED = (("placement_manager", "candidates", "export"),)
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    offline = op.get_context().as_sql
    tables = set() if offline else set(sa.inspect(op.get_bind()).get_table_names())
    if "saved_candidate_searches" not in tables:
        op.create_table(
            "saved_candidate_searches",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("owner_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("filters", sa.JSON(), nullable=False),
            sa.Column("shared", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        )
        op.create_index("uq_saved_candidate_searches_name", "saved_candidate_searches", ["owner_user_id", sa.text("lower(name)")], unique=True)
        op.create_index("ix_saved_candidate_searches_shared", "saved_candidate_searches", ["shared"])
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    # only `export`: hrc-002 declared the same resource's import/merge/erase keys, which other items own
    op.execute("DELETE FROM user_permission_overrides WHERE resource = 'candidates' AND action = 'export'")
    op.execute("DELETE FROM role_permissions WHERE resource = 'candidates' AND action = 'export'")
    op.drop_table("saved_candidate_searches")
