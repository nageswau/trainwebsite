"""nehn-018 -- student feature access by payment status: `student_access_rules` and the `student_access.configure` grant.

Revision ID: 0211_student_access_rules
Revises: 0210_training_report_grants

docs/superpowers/specs/2026-10-27-nehn-018-student-payment-access-design.md (DEC-SCOPE-304). 0001 builds a fresh database from the
current models, which already carry the table, so it is created only when missing (0194's idiom). Every feature is seeded at the
builder's default (`partially_paid`: the first payment unlocks the course). FEATURES / STATES are frozen copies of the model's tuples
at this revision. No existing row changes. The downgrade drops the table and deletes only this grant.
"""

import sqlalchemy as sa

from alembic import op

revision = "0211_student_access_rules"
down_revision = "0210_training_report_grants"
branch_labels = None
depends_on = None

FEATURES = ("attendance", "assignments", "assessments", "resources", "live_classes", "questions", "feedback", "certificates")
STATES = ("registered", "enrolled_pending_payment", "partially_paid", "fully_paid")
DEFAULT_MIN_STATE = "partially_paid"
SEED = (("it_admin", "student_access", "configure"),)


def upgrade() -> None:
    offline = op.get_context().as_sql
    tables = set() if offline else set(sa.inspect(op.get_bind()).get_table_names())
    if "student_access_rules" not in tables:
        op.create_table(
            "student_access_rules",
            sa.Column("feature", sa.String(30), primary_key=True),
            sa.Column("min_state", sa.String(30), nullable=False),
            sa.Column("updated_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(f"feature IN {FEATURES}", name="ck_student_access_rules_feature"),
            sa.CheckConstraint(f"min_state IN {STATES}", name="ck_student_access_rules_min_state"),
        )
    for feature in FEATURES:
        op.execute(sa.text("INSERT INTO student_access_rules (feature, min_state) VALUES (:feature, :state) ON CONFLICT DO NOTHING").bindparams(feature=feature, state=DEFAULT_MIN_STATE))
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("DELETE FROM role_permissions WHERE role = :role AND resource = :resource AND action = :action").bindparams(role=role, resource=resource, action=action))
    op.execute("DROP TABLE IF EXISTS student_access_rules")
