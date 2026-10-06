"""tel-002 -- tel_products (seeded with the 18 EVID-019 §3 values) and tel_campaigns.

Revision ID: 0076_tel_catalogue
Revises: 0075_telecaller_profiles

docs/superpowers/specs/2026-10-06-tel-002-catalogue-design.md §3 (DEC-SCOPE-074). Adds two tables; no existing row is read or written.
0001 builds a fresh database from the current models, which already carry both tables, so creation is guarded (0075's idiom) -- but the
seed always runs, and inserts only a (group, name) that is missing, so it is idempotent and never overwrites a manager's edit.
downgrade() refuses while manager data exists (any campaign, or a product that is not exactly a seed row).
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0076_tel_catalogue"
down_revision = "0075_telecaller_profiles"
branch_labels = None
depends_on = None

SOURCES = ("instagram", "facebook", "google", "website", "whatsapp", "walk_in", "college", "school", "agent", "referral", "exhibition_event", "bdm", "other")
# (group, name, team) in EVID-019 §3 order; T18 sets the "Other" teams (None = the unassigned queue).
SEED = (
    ("it", "Digital Marketing", "it"), ("it", "SAP", "it"), ("it", "Cyber Security", "it"), ("it", "Python Full Stack", "it"), ("it", "Java", "it"),
    ("overseas", "UK", "overseas"), ("overseas", "USA", "overseas"), ("overseas", "Canada", "overseas"), ("overseas", "Australia", "overseas"),
    ("overseas", "New Zealand", "overseas"), ("overseas", "Germany", "overseas"), ("overseas", "Japan", "overseas"),
    ("overseas", "South Korea", "overseas"), ("overseas", "Dubai", "overseas"),
    ("other", "Career Guidance", None), ("other", "Job Assistance", "it"), ("other", "Career Change", "it"), ("other", "General Enquiry", None),
)


def seed_statements():
    """One INSERT per seed row, skipped when that (group, lower(name)) already exists."""
    statement = (  # explicit casts: each parameter is used twice, and asyncpg refuses a type it deduces differently per use
        "INSERT INTO tel_products (id, product_group, name, team, sort_order) "
        "SELECT CAST(:id AS uuid), CAST(:group AS varchar), CAST(:name AS varchar), CAST(:team AS varchar), CAST(:sort AS integer) "
        "WHERE NOT EXISTS (SELECT 1 FROM tel_products WHERE product_group = CAST(:group AS varchar) AND lower(name) = lower(CAST(:name AS varchar)))"
    )
    return [(statement, {"id": uuid.uuid4(), "group": g, "name": n, "team": t, "sort": i}) for i, (g, n, t) in enumerate(SEED, start=1)]


def upgrade() -> None:
    bind = op.get_bind()
    if op.get_context().as_sql or "tel_products" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "tel_products",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("product_group", sa.String(20), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("team", sa.String(20), nullable=True),
            sa.Column("program_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("programs.id"), nullable=True),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("product_group IN ('it', 'overseas', 'other')", name="ck_tel_products_group"),
            sa.CheckConstraint("team IN ('it', 'overseas')", name="ck_tel_products_team"),
            sa.CheckConstraint("product_group = 'other' OR team = product_group", name="ck_tel_products_team_matches_group"),
            sa.CheckConstraint("program_id IS NULL OR product_group = 'it'", name="ck_tel_products_program_it_only"),
        )
        op.create_index("uq_tel_products_group_name", "tel_products", ["product_group", sa.text("lower(name)")], unique=True)
        op.create_table(
            "tel_campaigns",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("source", sa.String(30), nullable=False),
            sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tel_products.id"), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(f"source IN ({', '.join(repr(s) for s in SOURCES)})", name="ck_tel_campaigns_source"),
            sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_tel_campaigns_dates"),
        )
        op.create_index("uq_tel_campaigns_name", "tel_campaigns", [sa.text("lower(name)")], unique=True)
        op.create_index("ix_tel_campaigns_product", "tel_campaigns", ["product_id"])
    for statement, params in seed_statements():
        op.execute(sa.text(statement).bindparams(**params))


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        seed = sa.text(
            "SELECT count(*) FROM tel_products p WHERE p.program_id IS NULL AND p.active AND EXISTS (SELECT 1 FROM (VALUES "
            + ", ".join(f"(:g{i}, :n{i}, :t{i}, {i + 1})" for i in range(len(SEED)))
            + ") AS s(g, n, t, o) WHERE s.g = p.product_group AND s.n = p.name AND s.t IS NOT DISTINCT FROM p.team AND s.o = p.sort_order)"
        ).bindparams(*(sa.bindparam(f"t{i}", type_=sa.String) for i in range(len(SEED))))
        params = {k: v for i, (g, n, t) in enumerate(SEED) for k, v in ((f"g{i}", g), (f"n{i}", n), (f"t{i}", t))}
        untouched = bind.execute(seed, params).scalar()
        total = bind.execute(sa.text("SELECT count(*) FROM tel_products")).scalar()
        if bind.execute(sa.text("SELECT 1 FROM tel_campaigns LIMIT 1")).first() or untouched != total:
            raise RuntimeError("Cannot downgrade 0076_tel_catalogue: manager data exists (campaigns or edited products). Remove it deliberately first.")
    op.drop_table("tel_campaigns")
    op.drop_table("tel_products")
