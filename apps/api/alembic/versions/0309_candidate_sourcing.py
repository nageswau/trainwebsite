"""pob-018 -- source attribution, verification and outreach permission (DEC-SCOPE-428 A1-A6).

Revision ID: 0309_candidate_sourcing
Revises: 0308_vendor_requirements

docs/superpowers/specs/2026-11-08-pob-018-source-attribution-outreach-design.md. Additive: thirteen columns on `candidates` (all nullable
except `source_date` and `outreach_status`, which get a value for every existing row), four CHECKs, one partial index and four candidate
sources seeded when missing. `source_date` is backfilled to each candidate's `created_at` date in IST (A2). 0001 runs `create_all` from
today's models, so a fresh database already has everything: each step runs only when missing. CHECKS is a frozen copy of
`models.CANDIDATE_SOURCING_CHECKS`. The downgrade drops what the upgrade added except the catalogue values (candidates may point at them).
"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0309_candidate_sourcing"
down_revision = "0308_vendor_requirements"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_candidates_outreach_status": "outreach_status IS NULL OR outreach_status IN ('not_contacted', 'contacted', 'responded', 'consented', 'declined')",
    "ck_candidates_permission_method": (
        "outreach_permission_method IS NULL OR outreach_permission_method IN ('call', 'email', 'whatsapp', 'linkedin', 'in_person', 'form', 'other')"
    ),
    "ck_candidates_outreach_permission": (
        "(outreach_status = 'consented') = (outreach_permission_method IS NOT NULL) AND (outreach_permission_method IS NULL) = "
        "(outreach_permission_on IS NULL) AND (outreach_permission_on IS NULL) = (outreach_permission_by_user_id IS NULL)"
    ),
    "ck_candidates_referrer_self": "referrer_candidate_id IS NULL OR referrer_candidate_id <> id",
}
SOURCES = ("Vendor", "Website", "Community", "Institution")  # A1: "Website" is the name hrc-023 creates on first use
INDEX = "ix_candidates_vendor"


def _user(name: str) -> sa.Column:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)


COLUMNS = (
    lambda: sa.Column("source_date", sa.Date(), nullable=True),  # NOT NULL after the backfill
    lambda: sa.Column("referrer_name", sa.String(160), nullable=True),
    lambda: sa.Column("referrer_candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=True),
    lambda: sa.Column("vendor_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True),
    lambda: sa.Column("portal_import_reference", sa.String(120), nullable=True),
    lambda: sa.Column("last_verified_on", sa.Date(), nullable=True),
    lambda: _user("last_verified_by_user_id"),
    lambda: sa.Column("outreach_status", sa.String(16), server_default=sa.text("'not_contacted'"), nullable=False),
    lambda: sa.Column("outreach_status_changed_at", sa.DateTime(timezone=True), nullable=True),
    lambda: sa.Column("outreach_permission_method", sa.String(16), nullable=True),
    lambda: sa.Column("outreach_permission_on", sa.Date(), nullable=True),
    lambda: sa.Column("outreach_permission_note", sa.String(500), nullable=True),
    lambda: _user("outreach_permission_by_user_id"),
)


def _existing() -> tuple[set, set, set]:
    if op.get_context().as_sql:
        return set(), set(), set()
    inspector = sa.inspect(op.get_bind())
    return (
        {c["name"] for c in inspector.get_columns("candidates")},
        {c["name"] for c in inspector.get_check_constraints("candidates")},
        {i["name"] for i in inspector.get_indexes("candidates")},
    )


def upgrade() -> None:
    columns, checks, indexes = _existing()
    for make in COLUMNS:
        column = make()
        if column.name not in columns:
            op.add_column("candidates", column)
    op.execute("UPDATE candidates SET source_date = (created_at AT TIME ZONE 'Asia/Kolkata')::date WHERE source_date IS NULL")
    op.alter_column("candidates", "source_date", nullable=False, server_default=sa.func.current_date())
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "candidates", sql)
    if INDEX not in indexes:
        op.create_index(INDEX, "candidates", ["vendor_id"], postgresql_where=sa.text("vendor_id IS NOT NULL"))
    insert = sa.text(
        "INSERT INTO rec_candidate_sources (id, name, sort_order) SELECT CAST(:id AS uuid), CAST(:name AS varchar), "
        "(SELECT coalesce(max(sort_order), 0) + 1 FROM rec_candidate_sources) "
        "WHERE NOT EXISTS (SELECT 1 FROM rec_candidate_sources WHERE lower(name) = lower(CAST(:name AS varchar)))"
    )
    if not op.get_context().as_sql:
        for name in SOURCES:
            op.get_bind().execute(insert, {"id": uuid.uuid4(), "name": name})


def downgrade() -> None:
    op.drop_index(INDEX, table_name="candidates")
    for name in CHECKS:
        op.drop_constraint(name, "candidates", type_="check")
    for make in reversed(COLUMNS):
        op.drop_column("candidates", make().name)
