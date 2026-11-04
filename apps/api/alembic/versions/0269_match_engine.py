"""hrc-018 -- configurable matching engine: the admin factor weights and a job's optional hard filters.

Revision ID: 0269_match_engine
Revises: 0268_candidate_imports

docs/superpowers/specs/2026-11-04-hrc-018-matching-engine-design.md (DEC-SCOPE-392 E2/E6). Adds the one-row `match_settings` table (six
weights, each 0-100, summing to 100; no row = the defaults) and four `jobs.match_hard_*` switches, all false, so no existing ranking
filters differently. 0001 builds a fresh database from the current models, so each step runs only when missing (0251's idiom). The
downgrade drops both.
"""

import sqlalchemy as sa

from alembic import op

revision = "0269_match_engine"
down_revision = "0268_candidate_imports"
branch_labels = None
depends_on = None

FACTORS = ("skills", "experience", "qualification", "location", "role", "salary")
DEFAULT_WEIGHTS = (40, 20, 15, 10, 10, 5)
CHECKS = {
    "ck_match_settings_one_row": "id = 1",
    "ck_match_settings_range": " AND ".join(f"{f}_weight BETWEEN 0 AND 100" for f in FACTORS),
    "ck_match_settings_total": " + ".join(f"{f}_weight" for f in FACTORS) + " = 100",
}
HARD = ("experience", "qualification", "location", "salary")


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    if not _inspector().has_table("match_settings"):
        op.create_table(
            "match_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            *(sa.Column(f"{f}_weight", sa.SmallInteger(), nullable=False) for f in FACTORS),
            sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        )
    have = {c["name"] for c in _inspector().get_columns("jobs")}
    for key in HARD:
        if f"match_hard_{key}" not in have:
            op.add_column("jobs", sa.Column(f"match_hard_{key}", sa.Boolean(), server_default=sa.text("false"), nullable=False))


def downgrade() -> None:
    for key in HARD:
        op.drop_column("jobs", f"match_hard_{key}")
    op.drop_table("match_settings")
