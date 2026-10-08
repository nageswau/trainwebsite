"""rec-002 -- the recruiter managed lists (six simple lists, seeded) and rec_campaigns.

Revision ID: 0102_rec_catalogues
Revises: 0101_country_master

docs/superpowers/specs/2026-10-08-rec-002-recruiter-catalogues-design.md §3 (DEC-SCOPE-117). Adds seven tables; no existing row is read or
written. 0001 builds a fresh database from the current models, which already carry these tables, so creation is guarded (0076's idiom) --
but the seed always runs, and inserts only a name that is missing from its list, so it is idempotent and never overwrites a manager's edit.
downgrade() refuses while manager data exists (any campaign, or any list that is not exactly its seed).
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0102_rec_catalogues"
down_revision = "0101_country_master"
branch_labels = None
depends_on = None

# EVID-018 in source order (§2 lines 54-82, §9 440-462, §26 1029-1034, §4 184-192); industries start empty (C1); the owner's size bands (C2).
SEED = {
    "rec_lead_sources": (
        "LinkedIn",
        "College visits",
        "Job fairs",
        "Recruitment events",
        "Company visits",
        "Website",
        "Google",
        "Social media",
        "Referrals",
        "Existing clients",
        "BDM network",
        "Corporate database",
        "Cold calling",
        "Email campaigns",
        "WhatsApp campaigns",
    ),
    "rec_candidate_sources": (
        "College placements",
        "Edusphere students",
        "IT training students",
        "Job portals",
        "LinkedIn",
        "Referral",
        "Walk-ins",
        "Social media",
        "Career fairs",
        "Campus drives",
        "Database",
        "Employee referrals",
    ),
    "rec_industries": (),
    "rec_job_categories": ("IT", "Sales", "Marketing", "Finance", "HR", "Engineering"),
    "rec_contact_roles": ("HR Manager", "Talent Acquisition Manager", "Recruiter", "Hiring Manager", "HR Head"),
    "rec_company_sizes": ("1-10", "11-50", "51-200", "201-500", "501-1000", "1001+"),
}


def seed_statements():
    """One INSERT per seed value, skipped when that lower(name) is already in its list."""
    out = []
    for table, names in SEED.items():
        statement = (  # explicit casts: :name is used twice, and asyncpg refuses a type it deduces differently per use
            f"INSERT INTO {table} (id, name, sort_order) SELECT CAST(:id AS uuid), CAST(:name AS varchar), CAST(:sort AS integer) "
            f"WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE lower(name) = lower(CAST(:name AS varchar)))"
        )
        out += [(statement, {"id": uuid.uuid4(), "name": name, "sort": i}) for i, name in enumerate(names, start=1)]
    return out


def _columns():
    return (
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    if op.get_context().as_sql or "rec_lead_sources" not in sa.inspect(op.get_bind()).get_table_names():
        for table in SEED:
            op.create_table(table, *_columns())
            op.create_index(f"uq_{table}_name", table, [sa.text("lower(name)")], unique=True)
        op.create_table(
            "rec_campaigns",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("lead_source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rec_lead_sources.id"), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_rec_campaigns_dates"),
        )
        op.create_index("uq_rec_campaigns_name", "rec_campaigns", [sa.text("lower(name)")], unique=True)
        op.create_index("ix_rec_campaigns_lead_source", "rec_campaigns", ["lead_source_id"])
    for statement, params in seed_statements():
        op.execute(sa.text(statement).bindparams(**params))


def _is_seed(bind, table: str) -> bool:
    rows = bind.execute(sa.text(f"SELECT name, sort_order, active FROM {table}")).all()
    return sorted(rows) == sorted((name, i, True) for i, name in enumerate(SEED[table], start=1))


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        if bind.execute(sa.text("SELECT 1 FROM rec_campaigns LIMIT 1")).first() or not all(_is_seed(bind, table) for table in SEED):
            raise RuntimeError("Cannot downgrade 0102_rec_catalogues: manager data exists (campaigns or edited lists). Remove it deliberately first.")
    op.drop_table("rec_campaigns")
    for table in SEED:
        op.drop_table(table)
