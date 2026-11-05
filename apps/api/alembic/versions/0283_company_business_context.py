"""pob-003 -- company business context, last contact and the document store (DEC-SCOPE-406 D1-D6).

Revision ID: 0283_company_business_context
Revises: 0278_commercial_grants

docs/superpowers/specs/2026-11-05-pob-003-company-business-context-design.md. Additive only: four business-context columns and
`last_contacted_at` (indexed) on `companies`, and three new tables. No existing value changes; the legacy free-text `branches` is kept as
is. Every step is guarded (0001's `create_all` already builds today's
models on a fresh database). `last_contacted_at` is backfilled from the same sources the service recomputes it from (BACKFILL). DOCUMENT_KINDS is a frozen copy of
`models.COMPANY_DOCUMENT_KINDS`. The downgrade drops what the upgrade added (the stored files stay in object storage).
"""

import sqlalchemy as sa

from alembic import op

revision = "0283_company_business_context"
down_revision = "0278_commercial_grants"
branch_labels = None
depends_on = None

DOCUMENT_KINDS = ("company_profile", "vendor_onboarding_form", "recruitment_agreement", "job_description", "meeting_notes")
LISTS = ("departments_hiring", "hiring_locations", "target_roles")
BACKFILL = """
UPDATE companies c SET last_contacted_at = GREATEST(
    (SELECT max(occurred_at) FROM recruiter_calls WHERE company_id = c.id),
    (SELECT max(sent_at) FROM recruiter_messages WHERE company_id = c.id),
    (SELECT max(starts_at) FROM recruiter_meetings WHERE company_id = c.id AND status = 'completed')
)
"""


def _existing() -> tuple[set, set, set]:
    """0001 runs `create_all` from today's models, so a fresh database already has everything: each step runs only when missing."""
    if op.get_context().as_sql:
        return set(), set(), set()
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names()), {c["name"] for c in inspector.get_columns("companies")}, {i["name"] for i in inspector.get_indexes("companies")}


def upgrade() -> None:
    tables, columns, indexes = _existing()
    if "products_services" not in columns:
        op.add_column("companies", sa.Column("products_services", sa.String(2000), nullable=True))
    for column in LISTS:
        if column not in columns:
            op.add_column("companies", sa.Column(column, sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    if "last_contacted_at" not in columns:
        op.add_column("companies", sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True))
    if "ix_companies_last_contacted" not in indexes:
        op.create_index("ix_companies_last_contacted", "companies", ["last_contacted_at"])
    op.execute(BACKFILL)
    if "company_branches" not in tables:
        op.create_table(
            "company_branches",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False),
            sa.Column("city", sa.String(120), nullable=False),
            sa.Column("state", sa.String(120), nullable=True),
            sa.Column("country", sa.String(120), nullable=True),
        )
        op.create_index("ix_company_branches_company", "company_branches", ["company_id", "position"])
    if "company_skill_demand" not in tables:
        op.create_table(
            "company_skill_demand",
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("skill_id", sa.Uuid(), sa.ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True),
            sa.Column("position", sa.Integer(), nullable=False),
        )
        op.create_index("ix_company_skill_demand_skill_id", "company_skill_demand", ["skill_id"])
    if "company_documents" not in tables:
        op.create_table(
            "company_documents",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("kind", sa.String(40), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("content_type", sa.String(50), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("storage_key", sa.String(200), nullable=False),
            sa.Column("meeting_id", sa.Uuid(), sa.ForeignKey("recruiter_meetings.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("uploaded_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("kind IN (" + ", ".join(f"'{k}'" for k in DOCUMENT_KINDS) + ")", name="ck_company_documents_kind"),
        )
        op.create_index("ix_company_documents_company", "company_documents", ["company_id", "created_at"])
        op.create_index("ix_company_documents_meeting", "company_documents", ["meeting_id"])


def downgrade() -> None:
    op.drop_table("company_documents")
    op.drop_table("company_skill_demand")
    op.drop_table("company_branches")
    op.drop_index("ix_companies_last_contacted", table_name="companies")
    for column in ("last_contacted_at", *LISTS, "products_services"):
        op.drop_column("companies", column)
