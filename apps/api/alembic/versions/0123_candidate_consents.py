"""rec-010 -- candidate_consents.

Revision ID: 0123_candidate_consents
Revises: 0122_candidate_skills

docs/superpowers/specs/2026-10-09-rec-010-placement-pool-opt-in-design.md §2 (DEC-SCOPE-138). A new table only; no existing row changes.
0001 builds a fresh database from the current models, which already carry this table, so it is created only when missing (0119's idiom).
CHECKS repeats app.models.CANDIDATE_CONSENT_CHECKS (test_rec_010_migration). downgrade() refuses while any row exists: consent evidence is
never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0123_candidate_consents"
down_revision = "0122_candidate_skills"
branch_labels = None
depends_on = None

TABLE = "candidate_consents"
UUID = postgresql.UUID(as_uuid=True)
ACTIONS = ("opt_in", "opt_out")
CHECKS = {"ck_candidate_consents_action": f"action IN ({', '.join(repr(v) for v in ACTIONS)})"}  # must equal app.models.CANDIDATE_CONSENT_CHECKS


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("candidate_id", UUID, sa.ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("consent_version", sa.String(20), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_candidate_consents_candidate", TABLE, ["candidate_id", "created_at"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0123_candidate_consents: consent history exists. Keep it, or clear it deliberately first.")
    op.drop_table(TABLE)
