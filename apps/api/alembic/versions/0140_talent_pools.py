"""rec-015 -- talent pools: talent_pools (seeded with the six expressible S2-§8 examples).

Revision ID: 0140_talent_pools
Revises: 0139_recruiter_contracts

docs/superpowers/specs/2026-10-09-rec-015-talent-pools-design.md §2 (DEC-SCOPE-158). Additive: one new table, no existing row read or
written. 0001 builds a fresh database from the current models, which already carry the table, so creation is guarded (0104's idiom) --
but the seed always runs, inserting only a pool whose name (ignoring case) is missing, so it is idempotent and never overwrites a
manager's edit. EXPERIENCE_CHECK is a frozen copy of app.models.TALENT_POOL_EXPERIENCE_CHECK (test_rec_015_migration). downgrade()
refuses while a manager-made or manager-edited pool exists.
"""

import json
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0140_talent_pools"
down_revision = "0139_recruiter_contracts"
branch_labels = None
depends_on = None

TABLE = "talent_pools"
EXPERIENCE_CHECK = (
    "(experience_min_months IS NULL OR experience_min_months BETWEEN 0 AND 600) "
    "AND (experience_max_months IS NULL OR experience_max_months BETWEEN 0 AND 600) "
    "AND (experience_min_months IS NULL OR experience_max_months IS NULL OR experience_min_months <= experience_max_months)"
)
# P3: the S2-§8 examples the seeded Skills Master (0104) can express -- (name, all, any, min months, max months). P2: Freshers are 0
# years (0-11 months), Experienced Professionals 1 year or more. Cyber Security, SAP, Digital Marketing and Data Analysts need skills
# the Skills Master does not have yet, so the manager creates them.
SEED = (
    ("Java Developers", ["Java"], [], None, None),
    ("Python Developers", ["Python"], [], None, None),
    ("Full Stack Developers", [], [["HTML", "CSS", "JavaScript", "React", "Angular", "Vue.js"], ["Java", "Python", "PHP", "C#"]], None, None),
    ("Cloud Engineers", [], [["AWS", "Azure", "GCP"]], None, None),
    ("Freshers", [], [], None, 11),
    ("Experienced Professionals", [], [], 12, None),
)


def seed_statements() -> list[tuple[str, dict]]:
    return [
        (
            f"INSERT INTO {TABLE} (id, name, all_terms, any_terms, experience_min_months, experience_max_months) "
            "SELECT CAST(:id AS uuid), CAST(:name AS varchar), CAST(:all AS json), CAST(:any AS json), CAST(:min AS integer), CAST(:max AS integer) "
            f"WHERE NOT EXISTS (SELECT 1 FROM {TABLE} WHERE lower(name) = lower(CAST(:name AS varchar)))",
            {"id": uuid.uuid4(), "name": name, "all": json.dumps(all_terms), "any": json.dumps(any_terms), "min": low, "max": high},
        )
        for name, all_terms, any_terms, low, high in SEED
    ]


def upgrade() -> None:
    bind = op.get_bind()
    if op.get_context().as_sql or TABLE not in sa.inspect(bind).get_table_names():
        uuid_col = postgresql.UUID(as_uuid=True)
        op.create_table(
            TABLE,
            sa.Column("id", uuid_col, primary_key=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("all_terms", sa.JSON(), nullable=False),
            sa.Column("any_terms", sa.JSON(), nullable=False),
            sa.Column("experience_min_months", sa.Integer(), nullable=True),
            sa.Column("experience_max_months", sa.Integer(), nullable=True),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_by_user_id", uuid_col, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("updated_by_user_id", uuid_col, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(EXPERIENCE_CHECK, name="ck_talent_pools_experience"),
        )
        op.create_index("uq_talent_pools_name", TABLE, [sa.text("lower(name)")], unique=True)
    for sql, params in seed_statements():
        op.execute(sa.text(sql).bindparams(**params))


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(
        sa.text(f"SELECT 1 FROM {TABLE} WHERE created_by_user_id IS NOT NULL OR updated_by_user_id IS NOT NULL LIMIT 1")
    ).first():
        raise RuntimeError("Cannot downgrade 0140_talent_pools: managers have created or edited talent pools. Clear them deliberately first.")
    op.drop_table(TABLE)
