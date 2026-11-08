"""pob-019 -- candidate tags: the "Candidate tags" managed list (rec-002 shape) and the links from a candidate to its tags (DEC-SCOPE-439 T1/T2).

Revision ID: 0319_candidate_tags
Revises: 0318_placement_guarantee

docs/superpowers/specs/2026-11-08-pob-019-candidate-tags-bulk-actions-design.md. Additive only. 0001 builds a fresh database from the current
models, which already carry both tables, so each table is created only when missing. No seed: managers add the tags they use. The downgrade
drops both tables (links first).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0319_candidate_tags"
down_revision = "0318_placement_guarantee"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TAGS, LINKS = "rec_candidate_tags", "candidate_tag_links"


def _tables() -> set[str]:
    return set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if TAGS not in tables:
        op.create_table(
            TAGS,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(f"uq_{TAGS}_name", TAGS, [sa.text("lower(name)")], unique=True)
    if LINKS not in tables:
        op.create_table(
            LINKS,
            sa.Column("candidate_id", UUID, sa.ForeignKey("candidates.id", ondelete="RESTRICT"), primary_key=True),
            sa.Column("tag_id", UUID, sa.ForeignKey(f"{TAGS}.id", ondelete="RESTRICT"), primary_key=True),
            sa.Column("added_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_candidate_tag_links_tag", LINKS, ["tag_id"])


def downgrade() -> None:
    op.drop_table(LINKS)
    op.drop_table(TAGS)
