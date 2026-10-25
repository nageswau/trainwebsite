"""ccrm-006 -- the Duplicate closed stage, how a lead closed (`duplicate_of_id`, `lost_reason_id`, `lost_to` on `enquiries`) and the
admin-managed `lead_lost_reasons` list, seeded once.

Revision ID: 0185_lead_loss_capture
Revises: 0184_enrollment_confirmation

docs/superpowers/specs/2026-10-25-ccrm-006-lead-stages-loss-design.md (DEC-SCOPE-263). Additive. 0001 builds a fresh database from the
current models, which already carry all of this, so each step is guarded (0166's idiom); the status CHECK is always replaced (same
text on a fresh build). The stage list and CHECKs repeat app.models (test_ccrm_006_migration). The downgrade turns Duplicate leads into
Lost, so the old status CHECK holds, then drops the columns and the table.
"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0185_lead_loss_capture"
down_revision = "0184_enrollment_confirmation"
branch_labels = None
depends_on = None

LEADS, REASONS = "enquiries", "lead_lost_reasons"
OLD_STAGES = (
    "new",
    "assigned",
    "first_call_pending",
    "contacted",
    "qualified",
    "interested",
    "follow_up",
    "counselling_scheduled",
    "counselling_completed",
    "application_enrollment",
    "converted",
    "not_interested",
    "not_eligible",
    "wrong_number",
    "no_response",
    "lost",
)
STAGES = (*OLD_STAGES, "duplicate")
LOSS_STAGES = ("lost", "not_interested")


def _status_check(stages: tuple[str, ...]) -> str:
    return f"status IN ({', '.join(repr(s) for s in stages)})"


STATUS_CHECK = _status_check(STAGES)
_LOSS_SQL = f"status IN ({', '.join(repr(s) for s in LOSS_STAGES)})"
CLOSURE_CHECKS = {
    "ck_enquiries_duplicate_not_self": "duplicate_of_id IS NULL OR duplicate_of_id <> id",
    "ck_enquiries_duplicate_of": "(duplicate_of_id IS NOT NULL) = (status = 'duplicate')",
    "ck_enquiries_lost_reason": f"lost_reason_id IS NULL OR {_LOSS_SQL}",
    "ck_enquiries_lost_to": f"lost_to IS NULL OR ({_LOSS_SQL} AND length(lost_to) BETWEEN 1 AND 160)",
}
SEED = ("Fees / budget", "Chose another institution", "Chose another country", "Not ready this intake", "Not eligible for the course", "Other")


def lead_columns() -> tuple[sa.Column, ...]:  # fresh objects per call: a Column belongs to one table
    return (
        sa.Column("duplicate_of_id", sa.Uuid(), sa.ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("lost_reason_id", sa.Uuid(), sa.ForeignKey(f"{REASONS}.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("lost_to", sa.String(160), nullable=True),
    )


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything

    if inspector is None or not inspector.has_table(REASONS):
        op.create_table(
            REASONS,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("length(name) BETWEEN 1 AND 120", name="ck_lead_lost_reasons_name"),
        )
        op.create_index("uq_lead_lost_reasons_name", REASONS, [sa.text("lower(name)")], unique=True)
    if inspector is None or not op.get_bind().execute(sa.text(f"SELECT 1 FROM {REASONS} LIMIT 1")).first():
        table = sa.table(REASONS, sa.column("id", sa.Uuid()), sa.column("name", sa.String()), sa.column("sort_order", sa.Integer()))
        op.bulk_insert(table, [{"id": uuid.uuid4(), "name": name, "sort_order": i} for i, name in enumerate(SEED, start=1)])

    have = set() if inspector is None else {c["name"] for c in inspector.get_columns(LEADS)}
    for column in lead_columns():
        if column.name not in have:
            op.add_column(LEADS, column)
    op.drop_constraint("ck_enquiries_status", LEADS, type_="check")
    op.create_check_constraint("ck_enquiries_status", LEADS, STATUS_CHECK)
    checks = set() if inspector is None else {c["name"] for c in inspector.get_check_constraints(LEADS)}
    for name, sql in CLOSURE_CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, LEADS, sql)


def downgrade() -> None:
    for name in CLOSURE_CHECKS:
        op.drop_constraint(name, LEADS, type_="check")
    op.execute(f"UPDATE {LEADS} SET status = 'lost' WHERE status = 'duplicate'")
    op.drop_constraint("ck_enquiries_status", LEADS, type_="check")
    op.create_check_constraint("ck_enquiries_status", LEADS, _status_check(OLD_STAGES))
    for column in reversed(lead_columns()):
        op.drop_column(LEADS, column.name)
    op.drop_table(REASONS)
