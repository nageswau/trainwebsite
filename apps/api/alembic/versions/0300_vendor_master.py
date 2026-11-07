"""pob-010 -- the vendor master, onboarding and agreements (DEC-SCOPE-420 V2-V12).

Revision ID: 0300_vendor_master
Revises: 0299_requirement_checklist

docs/superpowers/specs/2026-11-07-pob-010-vendor-master-design.md. On `companies`: the vendor status and lists, and checks on `partner_type`
(it was an unchecked string; a value no code path writes is normalised to `recruiter`, logged with its count). New
`company_vendor_status_history`. The `nda` document kind. On `recruiter_contracts`: `party`, `direction`, `confidentiality_terms`, and the
one-current-row index becomes per party. `commercials.vendor.*` is seeded for the recruiters and their managers (a row that is there is left
alone).

Every step is guarded, because 0001's `create_all` already builds today's models on a fresh database. The checks are frozen copies of
`models.COMPANY_VENDOR_CHECKS` and `models.RECRUITER_CONTRACT_VENDOR_CHECKS`. The downgrade refuses while a vendor exists, because the
earlier schema cannot hold one.
"""

import logging

import sqlalchemy as sa

from alembic import op

revision = "0300_vendor_master"
down_revision = "0299_requirement_checklist"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

COMPANY_CHECKS = {
    "ck_companies_partner_type": "partner_type IN ('recruiter', 'employer', 'vendor', 'vendor_client')",
    "ck_companies_vendor_status": "vendor_status IS NULL OR vendor_status IN ('prospect', 'registration_submitted', 'approved', 'active', 'suspended')",
    "ck_companies_vendor_status_type": "(partner_type IN ('vendor', 'vendor_client')) = (vendor_status IS NOT NULL)",
}
CONTRACT_CHECKS = {
    "ck_recruiter_contracts_party": "party IN ('client', 'vendor')",
    "ck_recruiter_contracts_direction": "direction IS NULL OR direction IN ('vendor_pays_us', 'we_pay_vendor')",
    "ck_recruiter_contracts_vendor_terms": "party = 'vendor' OR (direction IS NULL AND confidentiality_terms IS NULL)",
}
LISTS = ("vendor_specialisations", "vendor_service_categories", "vendor_locations")
KINDS_BEFORE = ("company_profile", "vendor_onboarding_form", "recruitment_agreement", "job_description", "meeting_notes")
KINDS = (*KINDS_BEFORE, "nda")
GRANTS = tuple((role, "commercials.vendor", action) for role in ("placement_team", "placement_manager") for action in ("view", "edit"))
HISTORY = "company_vendor_status_history"
CURRENT = "uq_recruiter_contracts_current"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _checks(inspector, table: str) -> set:
    return {c["name"] for c in inspector.get_check_constraints(table)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    company_columns = {c["name"] for c in inspector.get_columns("companies")}
    contract_columns = {c["name"] for c in inspector.get_columns("recruiter_contracts")}
    if "vendor_status" not in company_columns:
        op.add_column("companies", sa.Column("vendor_status", sa.String(30), nullable=True))
    for column in LISTS:
        if column not in company_columns:
            op.add_column("companies", sa.Column(column, sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    unknown = op.get_bind().execute(sa.text("UPDATE companies SET partner_type = 'recruiter' WHERE partner_type NOT IN ('recruiter', 'employer', 'vendor', 'vendor_client')")).rowcount
    if unknown:
        logger.warning("pob-010: %s companies had an unknown partner_type and became 'recruiter'", unknown)
    present = _checks(inspector, "companies")
    for name, sql in COMPANY_CHECKS.items():
        if name not in present:
            op.create_check_constraint(name, "companies", sql)
    if not inspector.has_table(HISTORY):
        op.create_table(
            HISTORY,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("from_status", sa.String(30), nullable=False),
            sa.Column("to_status", sa.String(30), nullable=False),
            sa.Column("reason", sa.String(500), nullable=True),
            sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_company_vendor_status_history_company", HISTORY, ["company_id", "position"])
    op.execute("ALTER TABLE company_documents DROP CONSTRAINT IF EXISTS ck_company_documents_kind")
    op.create_check_constraint("ck_company_documents_kind", "company_documents", _in("kind", KINDS))
    if "party" not in contract_columns:
        op.add_column("recruiter_contracts", sa.Column("party", sa.String(10), nullable=False, server_default="client"))
    if "direction" not in contract_columns:
        op.add_column("recruiter_contracts", sa.Column("direction", sa.String(20), nullable=True))
    if "confidentiality_terms" not in contract_columns:
        op.add_column("recruiter_contracts", sa.Column("confidentiality_terms", sa.String(2000), nullable=True))
    present = _checks(inspector, "recruiter_contracts")
    for name, sql in CONTRACT_CHECKS.items():
        if name not in present:
            op.create_check_constraint(name, "recruiter_contracts", sql)
    index = next((i for i in inspector.get_indexes("recruiter_contracts") if i["name"] == CURRENT), None)
    if index is None or "party" not in index["column_names"]:
        op.execute(f"DROP INDEX IF EXISTS {CURRENT}")
        op.create_index(CURRENT, "recruiter_contracts", ["company_id", "party"], unique=True, postgresql_where=sa.text("is_current"))
    for role, resource, action in GRANTS:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM companies WHERE vendor_status IS NOT NULL OR partner_type IN ('vendor', 'vendor_client')")) or bind.scalar(sa.text("SELECT count(*) FROM company_documents WHERE kind = 'nda'")):
        raise RuntimeError("pob-010: vendors exist; the earlier schema cannot hold them")
    op.execute("DELETE FROM role_permissions WHERE resource = 'commercials.vendor'")
    op.execute(f"DROP INDEX IF EXISTS {CURRENT}")
    op.create_index(CURRENT, "recruiter_contracts", ["company_id"], unique=True, postgresql_where=sa.text("is_current"))
    for name in CONTRACT_CHECKS:
        op.drop_constraint(name, "recruiter_contracts", type_="check")
    for column in ("confidentiality_terms", "direction", "party"):
        op.drop_column("recruiter_contracts", column)
    op.execute("ALTER TABLE company_documents DROP CONSTRAINT IF EXISTS ck_company_documents_kind")
    op.create_check_constraint("ck_company_documents_kind", "company_documents", _in("kind", KINDS_BEFORE))
    op.drop_table(HISTORY)
    for name in COMPANY_CHECKS:
        op.drop_constraint(name, "companies", type_="check")
    for column in (*LISTS, "vendor_status"):
        op.drop_column("companies", column)
