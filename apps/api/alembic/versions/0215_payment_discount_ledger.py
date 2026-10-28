"""nehn-019 -- payment discount ledger: `payments.discount_amount`, `discount_reason`, `discounted_by_id` and `paid_at`.

Revision ID: 0215_payment_discount_ledger
Revises: 0211_student_access_rules

docs/superpowers/specs/2026-10-28-nehn-019-discount-ledger-complete-receipt-design.md (DEC-SCOPE-312). 0001 builds a fresh database
from the current models, which already carry the columns, so each one is added only when missing. Backfill (D12), where derivable:
the discount from the `payment.discount` audit rows (gross = the largest `original_amount`; reason and actor from the latest row),
`paid_at` from the payment's receipt. `amount` (the net payable) is never changed. The downgrade drops the four columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0215_payment_discount_ledger"
down_revision = "0211_student_access_rules"
branch_labels = None
depends_on = None

COLUMNS = (
    ("discount_amount", lambda: sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0")),
    ("discount_reason", lambda: sa.Column("discount_reason", sa.String(500), nullable=True)),
    ("discounted_by_id", lambda: sa.Column("discounted_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True)),
    ("paid_at", lambda: sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True)),
)

BACKFILL_DISCOUNT = """
UPDATE payments p SET discount_amount = d.gross - p.amount, discount_reason = LEFT(d.reason, 500), discounted_by_id = d.actor
FROM (
    SELECT DISTINCT ON (entity_id) entity_id,
           MAX((metadata_json->>'original_amount')::numeric) OVER (PARTITION BY entity_id) AS gross,
           metadata_json->>'reason' AS reason, user_id AS actor
    FROM audit_logs WHERE action = 'payment.discount' AND entity_type = 'payment'
    ORDER BY entity_id, created_at DESC
) d
WHERE d.entity_id = p.id::text AND d.gross > p.amount AND p.discount_amount = 0
"""

BACKFILL_PAID_AT = """
UPDATE payments p SET paid_at = r.issued_at FROM receipts r
WHERE r.payment_id = p.id AND p.paid_at IS NULL AND p.status IN ('paid', 'succeeded')
"""


def upgrade() -> None:
    offline = op.get_context().as_sql
    existing = set() if offline else {c["name"] for c in sa.inspect(op.get_bind()).get_columns("payments")}
    for name, column in COLUMNS:
        if name not in existing:
            op.add_column("payments", column())
    op.execute(BACKFILL_DISCOUNT)
    op.execute(BACKFILL_PAID_AT)


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("payments", name)
