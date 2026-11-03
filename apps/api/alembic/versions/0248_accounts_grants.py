"""itc-017 -- the accountant's default IT payment grants (Q-17) and an index on `payments.paid_at` for the collection reports.

Revision ID: 0248_accounts_grants
Revises: 0246_fee_adjustments

docs/superpowers/specs/2026-11-03-itc-017-accounts-workspace-design.md (DEC-SCOPE-367 F1, F8). Seed only: SEED is a frozen copy of the new
`rbac.DEFAULT_GRANTS["accountant"]` keys at this revision. A row that is already there (a super admin granted it) is left alone; no
existing row changes. The index is created only when missing (0001's create_all already builds it from the models). The downgrade removes
the three accountant rows and the index; other roles' grants are untouched.
"""

import sqlalchemy as sa

from alembic import op

revision = "0248_accounts_grants"
down_revision = "0246_fee_adjustments"
branch_labels = None
depends_on = None

SEED = (("accountant", "payments", "view"), ("accountant", "payments", "add"), ("accountant", "payments", "refund"))
INDEX = "ix_payments_paid_at"


def _offline() -> bool:
    return op.get_context().as_sql


def upgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))
    if _offline() or INDEX not in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("payments")}:
        op.create_index(INDEX, "payments", ["paid_at"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name="payments")
    op.execute("DELETE FROM role_permissions WHERE role = 'accountant' AND resource = 'payments' AND action IN ('view', 'add', 'refund')")
