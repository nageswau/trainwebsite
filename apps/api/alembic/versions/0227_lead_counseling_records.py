"""itc-010 -- the IT counseling record: lead_counseling_objections, lead_counseling_records, lead_counseling_record_objections.

Revision ID: 0227_lead_counseling_records
Revises: 0226_follow_up_escalation

docs/superpowers/specs/2026-11-02-itc-010-it-counseling-record-design.md (DEC-SCOPE-343). Additive: no existing row changes. 0001 builds a
fresh database from the current models, which already carry the tables, so each is created only when missing (0186's idiom); the
objection list is seeded only when empty. downgrade() refuses while counseling records exist: a counselor's sessions are not dropped
silently.
"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0227_lead_counseling_records"
down_revision = "0226_follow_up_escalation"
branch_labels = None
depends_on = None

OBJECTIONS, RECORDS, LINKS = "lead_counseling_objections", "lead_counseling_records", "lead_counseling_record_objections"
DECISION_MAKERS = ("self", "parent", "spouse", "employer", "other")
OUTCOMES = ("interested", "needs_time", "not_interested", "enrolled")
CHECKS = {  # the model's LEAD_COUNSELING_CHECKS, frozen here (test_itc_010_migration asserts they stay identical)
    "ck_lead_counseling_records_decision_maker": "decision_maker IS NULL OR decision_maker IN ({})".format(", ".join(repr(v) for v in DECISION_MAKERS)),
    "ck_lead_counseling_records_outcome": "outcome IN ({})".format(", ".join(repr(v) for v in OUTCOMES)),
    "ck_lead_counseling_records_fee": "fee_quoted IS NULL OR fee_quoted >= 0",
    "ck_lead_counseling_records_notes": "notes IS NULL OR length(notes) <= 4000",
    "ck_lead_counseling_records_objection_notes": "objection_notes IS NULL OR length(objection_notes) <= 1000",
}
# C6 builder default (NEEDS_CONFIRMATION): the common IT counseling objections; managers rename, reorder or deactivate them.
SEED = ("Fee too high", "Needs time to decide", "Family approval needed", "Batch timing does not suit", "Comparing other institutes", "Unsure about job outcome")


def _uuid():
    return sa.Uuid()


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything

    def missing(table: str) -> bool:
        return inspector is None or not inspector.has_table(table)

    if missing(OBJECTIONS):
        op.create_table(
            OBJECTIONS,
            sa.Column("id", _uuid(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("length(name) BETWEEN 1 AND 120", name="ck_lead_counseling_objections_name"),
        )
        op.create_index("uq_lead_counseling_objections_name", OBJECTIONS, [sa.text("lower(name)")], unique=True)
    if missing(RECORDS):
        op.create_table(
            RECORDS,
            sa.Column("id", _uuid(), primary_key=True),
            sa.Column("lead_id", _uuid(), sa.ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("author_user_id", _uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("updated_by_user_id", _uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("recommended_product_id", _uuid(), sa.ForeignKey("tel_products.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("objection_notes", sa.Text(), nullable=True),
            sa.Column("fee_quoted", sa.Numeric(12, 2), nullable=True),
            sa.Column("expected_joining_date", sa.Date(), nullable=True),
            sa.Column("decision_maker", sa.String(20), nullable=True),
            sa.Column("outcome", sa.String(20), nullable=False),
            sa.Column("next_follow_up", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        )
        op.create_index("ix_lead_counseling_records_lead_created", RECORDS, ["lead_id", "created_at"])
    if missing(LINKS):
        op.create_table(
            LINKS,
            sa.Column("record_id", _uuid(), sa.ForeignKey(f"{RECORDS}.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("objection_id", _uuid(), sa.ForeignKey(f"{OBJECTIONS}.id", ondelete="RESTRICT"), primary_key=True),
        )
    if inspector is None or not op.get_bind().execute(sa.text(f"SELECT 1 FROM {OBJECTIONS} LIMIT 1")).first():
        table = sa.table(OBJECTIONS, sa.column("id", sa.Uuid()), sa.column("name", sa.String()), sa.column("sort_order", sa.Integer()))
        op.bulk_insert(table, [{"id": uuid.uuid4(), "name": name, "sort_order": i} for i, name in enumerate(SEED, start=1)])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {RECORDS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0227: IT counseling records exist (itc-010)")
    op.drop_table(LINKS)
    op.drop_index("ix_lead_counseling_records_lead_created", table_name=RECORDS)
    op.drop_table(RECORDS)
    op.drop_index("uq_lead_counseling_objections_name", table_name=OBJECTIONS)
    op.drop_table(OBJECTIONS)
