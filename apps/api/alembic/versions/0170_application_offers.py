"""ccrm-023 -- offer records with history: application_offers, the widened offer-type CHECK, and the backfill.

Revision ID: 0170_application_offers
Revises: 0169_lead_next_action, 0169_overseas_student_notes

docs/superpowers/specs/2026-10-23-ccrm-023-application-offers-design.md (DEC-SCOPE-245). Also merges main's two 0169 heads. 0001
builds a fresh database from the current models, which already carry the table, so it is created only when missing (0166's idiom). The
backfill turns each application offer recorded in the columns (AGN-010) into one active row, once (NOT EXISTS). TYPES and STATUSES
repeat app.models.APPLICATION_OFFER_TYPES / _STATUSES (test_ccrm_023_migration). downgrade() drops the table and restores the
two-type CHECK, which fails loudly while a pathway/other offer is mirrored.
"""

import sqlalchemy as sa

from alembic import op

revision = "0170_application_offers"
down_revision = ("0169_lead_next_action", "0169_overseas_student_notes")
branch_labels = None
depends_on = None

TABLE = "application_offers"
TYPES = ("conditional", "unconditional", "pathway", "other")
STATUSES = ("active", "superseded", "withdrawn_by_university", "expired")
APP_CHECK = "ck_overseas_applications_offer_type"
BACKFILL = """
INSERT INTO application_offers (id, application_id, offer_type, issue_date, offer_deadline, conditions, offer_document_id, status, created_at, updated_at)
SELECT gen_random_uuid(), a.id, a.offer_type, a.offer_date, a.offer_deadline, a.offer_conditions, a.offer_document_id, 'active', now(), now()
FROM overseas_applications a
WHERE a.offer_type IS NOT NULL AND NOT EXISTS (SELECT 1 FROM application_offers o WHERE o.application_id = a.id)
"""


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _missing() -> bool:
    return op.get_context().as_sql or TABLE not in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _missing():
        op.create_table(
            TABLE,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("application_id", sa.Uuid(), sa.ForeignKey("overseas_applications.id"), nullable=False),
            sa.Column("offer_type", sa.String(20), nullable=False),
            sa.Column("issue_date", sa.Date(), nullable=False),
            sa.Column("offer_deadline", sa.Date(), nullable=True),
            sa.Column("conditions", sa.Text(), nullable=True),
            sa.Column("currency", sa.String(3), nullable=True),
            sa.Column("tuition_amount", sa.Numeric(12, 2), nullable=True),
            sa.Column("scholarship_amount", sa.Numeric(12, 2), nullable=True),
            sa.Column("deposit_amount", sa.Numeric(12, 2), nullable=True),
            sa.Column("deposit_deadline", sa.Date(), nullable=True),
            sa.Column("offer_document_id", sa.Uuid(), sa.ForeignKey("student_documents.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'active'")),
            sa.Column("status_reason", sa.Text(), nullable=True),
            sa.Column("recorded_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("closed_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint(f"offer_type IN {_in(TYPES)}", name="ck_application_offers_type"),
            sa.CheckConstraint(f"status IN {_in(STATUSES)}", name="ck_application_offers_status"),
            sa.CheckConstraint("status IN ('active', 'superseded') OR status_reason IS NOT NULL", name="ck_application_offers_reason"),
            sa.CheckConstraint("(currency IS NULL) = (tuition_amount IS NULL AND scholarship_amount IS NULL AND deposit_amount IS NULL)", name="ck_application_offers_currency"),
            sa.CheckConstraint("tuition_amount >= 0 AND scholarship_amount >= 0 AND deposit_amount >= 0", name="ck_application_offers_amounts"),
        )
        op.create_index("uq_application_offers_active", TABLE, ["application_id"], unique=True, postgresql_where=sa.text("status = 'active'"))
        op.create_index("ix_application_offers_application", TABLE, ["application_id", "created_at"])
    op.drop_constraint(APP_CHECK, "overseas_applications", type_="check")
    op.create_check_constraint(APP_CHECK, "overseas_applications", f"offer_type IS NULL OR offer_type IN {_in(TYPES)}")
    op.execute(BACKFILL)


def downgrade() -> None:
    op.drop_table(TABLE)
    op.drop_constraint(APP_CHECK, "overseas_applications", type_="check")
    op.create_check_constraint(APP_CHECK, "overseas_applications", "offer_type IS NULL OR offer_type IN ('conditional', 'unconditional')")
