"""rec-030 -- recruiter contracts / MoU: recruiter_contracts and recruiter_contract_events.

Revision ID: 0139_recruiter_contracts
Revises: 0138_offer_management

docs/superpowers/specs/2026-10-09-rec-030-recruiter-contracts-design.md §2 (DEC-SCOPE-156). Additive: two new tables, no existing row read
or written. 0001 builds a fresh database from the current models, which already carry both tables, so each is created only when
missing. STATUSES / EVENT_KINDS / CHECKS are frozen copies of app.models.RECRUITER_CONTRACT_* (test_rec_030_migration). downgrade()
refuses while any contract exists: recorded agreements are never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0139_recruiter_contracts"
down_revision = "0138_offer_management"
branch_labels = None
depends_on = None

CONTRACTS = "recruiter_contracts"
EVENTS = "recruiter_contract_events"
STATUSES = ("discussion", "proposal_sent", "negotiation", "contract_sent", "signed", "active")
FEE_BASES = ("fixed", "percent_of_ctc")
EVENT_KINDS = ("created", "status", "updated", "document", "renewed")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {
    "ck_recruiter_contracts_status": _in_list("status", STATUSES),
    "ck_recruiter_contracts_window": "start_date IS NULL OR end_date IS NULL OR end_date >= start_date",
    "ck_recruiter_contracts_fee_pair": "(fee_basis IS NULL) = (fee_value IS NULL)",
    "ck_recruiter_contracts_fee_basis": "fee_basis IS NULL OR " + _in_list("fee_basis", FEE_BASES),
    "ck_recruiter_contracts_fee_value": "fee_value IS NULL OR (fee_value >= 0 AND (fee_basis <> 'percent_of_ctc' OR fee_value <= 100))",
    "ck_recruiter_contracts_signed_document": "status NOT IN ('signed', 'active') OR contract_document_key IS NOT NULL",
    "ck_recruiter_contracts_active_window": "status <> 'active' OR (start_date IS NOT NULL AND end_date IS NOT NULL)",
    "ck_recruiter_contracts_contract_document": "(contract_document_key IS NULL) = (contract_document_content_type IS NULL)",
    "ck_recruiter_contracts_mou_document": "(mou_document_key IS NULL) = (mou_document_content_type IS NULL)",
}


def _tables() -> set[str]:
    if op.get_context().as_sql:  # offline SQL: emit everything
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def _document(prefix: str) -> list[sa.Column]:
    return [
        sa.Column(f"{prefix}_document_key", sa.String(200), nullable=True),
        sa.Column(f"{prefix}_document_content_type", sa.String(50), nullable=True),
        sa.Column(f"{prefix}_document_name", sa.String(255), nullable=True),
        sa.Column(f"{prefix}_document_uploaded_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    tables = _tables()
    uuid = postgresql.UUID(as_uuid=True)
    if CONTRACTS not in tables:
        op.create_table(
            CONTRACTS,
            sa.Column("id", uuid, primary_key=True),
            sa.Column("company_id", uuid, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="discussion"),
            sa.Column("status_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("agreement_type", sa.String(100), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("fee_basis", sa.String(20), nullable=True),
            sa.Column("fee_value", sa.Numeric(12, 2), nullable=True),
            sa.Column("payment_terms", sa.String(2000), nullable=True),
            sa.Column("replacement_policy", sa.String(2000), nullable=True),
            *_document("contract"),
            *_document("mou"),
            sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        )
        op.create_index("uq_recruiter_contracts_current", CONTRACTS, ["company_id"], unique=True, postgresql_where=sa.text("is_current"))
        op.create_index("ix_recruiter_contracts_company", CONTRACTS, ["company_id", "created_at"])
    if EVENTS not in tables:
        op.create_table(
            EVENTS,
            sa.Column("id", uuid, primary_key=True),
            sa.Column("contract_id", uuid, sa.ForeignKey("recruiter_contracts.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("actor_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("from_status", sa.String(20), nullable=True),
            sa.Column("to_status", sa.String(20), nullable=False),
            sa.Column("changed", sa.JSON(), nullable=False),
            sa.Column("document_key", sa.String(200), nullable=True),
            sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(_in_list("kind", EVENT_KINDS), name="ck_recruiter_contract_events_kind"),
        )
        op.create_index("ix_recruiter_contract_events_contract", EVENTS, ["contract_id", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {CONTRACTS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0139_recruiter_contracts: recruiter contracts exist. Clear them deliberately first.")
    op.drop_table(EVENTS)
    op.drop_table(CONTRACTS)
