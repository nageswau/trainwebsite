"""itc-011 -- the one-step IT conversion: the onboarding checklist template (seeded), each enrolment's checklist and the conversion log.

Revision ID: 0243_it_conversion
Revises: 0241_enrollment_lifecycle

docs/superpowers/specs/2026-11-03-itc-011-it-one-step-conversion-design.md (C1, C8). Three new tables; no existing row changes. 0001
builds a fresh database from the current models, which already carry the tables, so each step is guarded (0222's idiom) and the five
template items are seeded only into an empty template. The downgrade drops the three tables (the checklists and the log go with them).
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0243_it_conversion"
down_revision = "0241_enrollment_lifecycle"
branch_labels = None
depends_on = None

TEMPLATE, ITEMS, CONVERSIONS = "it_onboarding_template_items", "it_onboarding_items", "it_conversions"
# C1 (NEEDS_CONFIRMATION, Q-09): neutral starting items; the IT team edits them once a template editor exists.
DEFAULT_ITEMS = (
    "Set your password and sign in",
    "Accept the enrolment agreement",
    "Upload a photo ID proof",
    "Upload your qualification certificate",
    "Attend the batch orientation",
)


def _offline() -> bool:
    return op.get_context().as_sql


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    inspector = None if _offline() else sa.inspect(op.get_bind())
    tables = set() if inspector is None else set(inspector.get_table_names())
    if TEMPLATE not in tables:
        op.create_table(
            TEMPLATE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("label", sa.String(200), nullable=False),
            sa.Column("position", sa.Integer, nullable=False),
            sa.Column("active", sa.Boolean, server_default=sa.text("true"), nullable=False),
            *_timestamps(),
        )
    if ITEMS not in tables:
        op.create_table(
            ITEMS,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
            sa.Column("label", sa.String(200), nullable=False),
            sa.Column("position", sa.Integer, nullable=False),
            sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("done_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            *_timestamps(),
        )
        op.create_index("ix_it_onboarding_items_enrollment", ITEMS, ["enrollment_id", "position"])
    if CONVERSIONS not in tables:
        op.create_table(
            CONVERSIONS,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("lead_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enquiries.id"), nullable=False),
            sa.Column("idempotency_key", sa.String(120), nullable=False),
            sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("student_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enrollments.id"), nullable=False),
            sa.Column("created_account", sa.Boolean, nullable=False),
            *_timestamps(),
            sa.UniqueConstraint("lead_id", "idempotency_key", name="uq_it_conversions_lead_key"),
        )
    empty = inspector is None or not op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {TEMPLATE})"))
    if empty:
        table = sa.table(TEMPLATE, sa.column("id", postgresql.UUID(as_uuid=True)), sa.column("label", sa.String), sa.column("position", sa.Integer))
        op.bulk_insert(table, [{"id": uuid.uuid4(), "label": label, "position": i} for i, label in enumerate(DEFAULT_ITEMS, start=1)])


def downgrade() -> None:
    op.drop_table(CONVERSIONS)
    op.drop_table(ITEMS)
    op.drop_table(TEMPLATE)
