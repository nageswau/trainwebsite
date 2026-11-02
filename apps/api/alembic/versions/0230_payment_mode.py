"""itc-013 -- per-enrolment fee account: the payment mode.

Revision ID: 0230_payment_mode
Revises: 0229_it_student_profiles

DEC-SCOPE-346. `payments` gains `payment_mode` (nullable; one of MODES), shown with the transaction reference on the receipt. Only a
confirmed gateway payment is known to have been made through Razorpay, so only those rows are backfilled; every other existing row
keeps an unknown (NULL) mode rather than a guessed one. The fee account itself is computed from `payments` (Q-13), so it needs no table.
0001 builds a fresh database from the current models, so the column is added only when missing and the CHECK is dropped and re-created.
The column only ever holds the mode, so the downgrade drops it.
"""

from alembic import op

revision = "0230_payment_mode"
down_revision = "0229_it_student_profiles"
branch_labels = None
depends_on = None

MODES = ("cash", "upi", "card", "bank_transfer", "cheque", "razorpay")  # frozen copy of models.PAYMENT_MODES


def upgrade() -> None:
    op.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_mode VARCHAR(20)")
    op.execute("ALTER TABLE payments DROP CONSTRAINT IF EXISTS ck_payments_payment_mode")
    op.execute(f"ALTER TABLE payments ADD CONSTRAINT ck_payments_payment_mode CHECK (payment_mode IS NULL OR payment_mode IN ({', '.join(repr(m) for m in MODES)}))")
    op.execute("UPDATE payments SET payment_mode = 'razorpay' WHERE payment_mode IS NULL AND provider = 'razorpay' AND status IN ('paid', 'succeeded')")


def downgrade() -> None:
    op.execute("ALTER TABLE payments DROP CONSTRAINT IF EXISTS ck_payments_payment_mode")
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS payment_mode")
