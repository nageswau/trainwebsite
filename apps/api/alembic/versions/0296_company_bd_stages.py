"""pob-004 -- the BD pipeline: three more company stages, the client status, the Inactive flag and the two reason lists.

Revision ID: 0296_company_bd_stages
Revises: 0295_recruitment_report_grants

docs/superpowers/specs/2026-11-06-pob-004-bd-pipeline-stages-design.md (DEC-SCOPE-417). 0001 builds a fresh database from today's models, so every
object is created only when missing. Only `client_status` is backfilled (a current client must not read as a prospect); no stage or history row
changes. downgrade() refuses while a company sits at a new stage or is inactive.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0296_company_bd_stages"
down_revision = "0295_recruitment_report_grants"
branch_labels = None
depends_on = None

TABLE = "companies"
UUID = postgresql.UUID(as_uuid=True)
LOST, INACTIVE = "rec_company_lost_reasons", "rec_company_inactive_reasons"
# Frozen copies: of app.recruiter_stages.ORDER at this revision (test_pob_004_migration checks parity), and of 0112's list for the downgrade.
STAGES = (
    "new_lead", "research_completed", "hr_contact_identified", "contacted", "interested", "meeting_scheduled", "requirement_discussion", "vendor_registration",
    "requirement_received", "jd_received", "candidates_sourcing", "profiles_shared", "interview", "selected", "joined", "requirement_closed",
)  # fmt: skip
NEW_STAGES = ("research_completed", "hr_contact_identified", "vendor_registration")
OLD_STAGES = tuple(s for s in STAGES if s not in NEW_STAGES)
STAGE_CHECK = "ck_companies_stage"
CHECKS = {  # must equal app.models.COMPANY_PIPELINE_CHECKS
    "ck_companies_inactive": "(inactive_at IS NULL) = (inactive_reason IS NULL)",
    "ck_companies_client_status": "client_status IN ('prospect', 'active_client', 'repeat_business')",
}
SEED = {
    LOST: ("Not hiring at present", "Chose another vendor", "Fee or terms not agreed", "No response", "Not a fit for our candidates", "Other"),
    INACTIVE: ("No current hiring", "Contact left the company", "No response", "On hold by the company", "Other"),
}
RECEIVED = "SELECT 1 FROM jobs j JOIN job_status_history h ON h.job_id = j.id WHERE j.company_id = companies.id AND h.to_status = 'requirement_received'"
SIGNED = "SELECT 1 FROM recruiter_contracts c WHERE c.company_id = companies.id AND c.status IN ('signed', 'active')"
REPEAT = """
    SELECT 1 FROM job_offers o
    JOIN job_applications a ON a.id = o.application_id
    JOIN jobs joined ON joined.id = a.job_id
    JOIN jobs later ON later.company_id = joined.company_id AND later.id <> joined.id
    JOIN job_status_history h ON h.job_id = later.id AND h.to_status = 'requirement_received'
    WHERE joined.company_id = companies.id AND o.joining_status = 'joined' AND h.created_at::date >= o.actual_joining_date
"""


def _stage_sql(stages: tuple[str, ...]) -> str:
    return "stage IN (" + ", ".join(f"'{s}'" for s in stages) + ")"


def _inspect():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspect()
    tables = set(inspector.get_table_names()) if inspector else set()
    for table in SEED:
        if table not in tables:
            op.create_table(
                table,
                sa.Column("id", UUID, primary_key=True),
                sa.Column("name", sa.String(120), nullable=False),
                sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
                sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
                sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
                sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            )
            op.create_index(f"uq_{table}_name", table, [sa.text("lower(name)")], unique=True)
    for table, names in SEED.items():
        statement = (
            f"INSERT INTO {table} (id, name, sort_order) SELECT CAST(:id AS uuid), CAST(:name AS varchar), CAST(:sort AS integer) "
            f"WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE lower(name) = lower(CAST(:name AS varchar)))"
        )
        for i, name in enumerate(names, start=1):
            op.execute(sa.text(statement).bindparams(id=uuid.uuid4(), name=name, sort=i))

    columns = {c["name"] for c in inspector.get_columns(TABLE)} if inspector else set()
    if "lost_reason_id" not in columns:
        op.add_column(TABLE, sa.Column("lost_reason_id", UUID, sa.ForeignKey(f"{LOST}.id", ondelete="RESTRICT"), nullable=True))
    if "inactive_at" not in columns:
        op.add_column(TABLE, sa.Column("inactive_at", sa.DateTime(timezone=True), nullable=True))
    if "inactive_reason" not in columns:
        op.add_column(TABLE, sa.Column("inactive_reason", sa.String(500), nullable=True))
    if "inactive_reason_id" not in columns:
        op.add_column(TABLE, sa.Column("inactive_reason_id", UUID, sa.ForeignKey(f"{INACTIVE}.id", ondelete="RESTRICT"), nullable=True))
    if "client_status" not in columns:
        op.add_column(TABLE, sa.Column("client_status", sa.String(20), nullable=False, server_default="prospect"))

    checks = {c["name"] for c in inspector.get_check_constraints(TABLE)} if inspector else set()
    if STAGE_CHECK in checks:
        op.drop_constraint(STAGE_CHECK, TABLE, type_="check")
    op.create_check_constraint(STAGE_CHECK, TABLE, _stage_sql(STAGES))
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)

    op.execute(f"UPDATE {TABLE} SET client_status = 'active_client' WHERE client_status = 'prospect' AND (EXISTS ({RECEIVED}) OR EXISTS ({SIGNED}))")
    op.execute(f"UPDATE {TABLE} SET client_status = 'repeat_business' WHERE client_status = 'active_client' AND EXISTS ({REPEAT})")


def downgrade() -> None:
    if not op.get_context().as_sql:
        new = ", ".join(f"'{s}'" for s in NEW_STAGES)
        used = f"SELECT 1 FROM {TABLE} WHERE stage IN ({new}) OR inactive_at IS NOT NULL LIMIT 1"
        if op.get_bind().execute(sa.text(used)).first():
            raise RuntimeError("Cannot downgrade 0296_company_bd_stages: a company sits at a new stage or is inactive. Clear it deliberately first.")
    op.drop_constraint(STAGE_CHECK, TABLE, type_="check")
    op.create_check_constraint(STAGE_CHECK, TABLE, _stage_sql(OLD_STAGES))
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    for name in ("client_status", "inactive_reason_id", "inactive_reason", "inactive_at", "lost_reason_id"):
        op.drop_column(TABLE, name)
    for table in SEED:
        op.drop_table(table)
