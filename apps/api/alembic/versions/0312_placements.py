"""pob-024 -- the placement closure record: `placements` (one per accepted offer, its confirmations and the invoice draft).

Revision ID: 0312_placements
Revises: 0310_sourcing_plans

docs/superpowers/specs/2026-11-08-pob-024-placement-closure-design.md (DEC-SCOPE-432). Additive. 0001 builds a fresh database from the current
models, which already carry this table, so it is created only when missing. CHECKS is a frozen copy of `models.PLACEMENT_RECORD_CHECKS`. No
backfill: an offer accepted before this revision gets its placement when it is joined (P1). The downgrade drops the table.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0312_placements"
down_revision = "0310_sourcing_plans"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_placements_invoice_status": "invoice_status IN ('none', 'draft', 'issued', 'discarded')",
    "ck_placements_candidate_via": "candidate_confirmed_via IS NULL OR candidate_confirmed_via IN ('call', 'email', 'whatsapp', 'in_person', 'other')",
    "ck_placements_client_via": "client_confirmed_via IS NULL OR client_confirmed_via IN ('call', 'email', 'whatsapp', 'in_person', 'other')",
    "ck_placements_amounts": "(expected_fee IS NULL OR expected_fee >= 0) AND (draft_amount IS NULL OR draft_amount > 0)",
    "ck_placements_issued": "(invoice_status = 'issued') = (invoice_id IS NOT NULL)",
    "ck_placements_draft": "invoice_status = 'none' OR draft_due_date IS NOT NULL",
    "ck_placements_discarded": "(invoice_status = 'discarded') = (draft_discard_reason IS NOT NULL)",
}
UUID = postgresql.UUID(as_uuid=True)


def _user(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)


def upgrade() -> None:
    offline = op.get_context().as_sql
    if not offline and "placements" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "placements",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("offer_id", UUID, sa.ForeignKey("job_offers.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("application_id", UUID, sa.ForeignKey("job_applications.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("job_id", UUID, sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_id", UUID, sa.ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("vendor_company_id", UUID, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("role", sa.String(200), nullable=False),
        _user("recruiter_user_id"),
        _user("po_owner_user_id"),
        sa.Column("expected_fee", sa.Numeric(12, 2), nullable=True),
        sa.Column("candidate_confirmed_by", sa.String(160), nullable=True),
        sa.Column("candidate_confirmed_on", sa.Date(), nullable=True),
        sa.Column("candidate_confirmed_via", sa.String(12), nullable=True),
        sa.Column("client_confirmed_by", sa.String(160), nullable=True),
        sa.Column("client_confirmed_on", sa.Date(), nullable=True),
        sa.Column("client_confirmed_via", sa.String(12), nullable=True),
        sa.Column("invoice_status", sa.String(10), nullable=False, server_default=sa.text("'none'")),
        sa.Column("draft_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("draft_due_date", sa.Date(), nullable=True),
        sa.Column("draft_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("draft_discard_reason", sa.String(500), nullable=True),
        sa.Column("invoice_id", UUID, sa.ForeignKey("recruiter_invoices.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("due_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overdue_notified_at", sa.DateTime(timezone=True), nullable=True),
        _user("created_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_placements_job", "placements", ["job_id"])
    op.create_index("ix_placements_invoice_status", "placements", ["invoice_status"])


def downgrade() -> None:
    op.drop_table("placements")
