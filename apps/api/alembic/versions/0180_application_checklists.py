"""ccrm-019 -- an application's document checklist (application_checklists, application_checklist_items,
application_checklist_item_documents) and overseas_applications.documents_completed_on.

Revision ID: 0180_application_checklists
Revises: 0178_offer_decisions_deposits

docs/superpowers/specs/2026-10-24-ccrm-019-application-checklist-design.md (DEC-SCOPE-257). Nothing is backfilled: a checklist is made
when the counselor creates it or the gate first needs it. ccrm-013 (0179, built in parallel) adds the same `documents_completed_on`
column, so it is added only when missing. 0001 builds a fresh database from the current models, so each step runs only when missing
(0166's idiom). MARKS / GATE_MODES repeat app.application_checklists / app.document_checklists (test_ccrm_019_migration). The downgrade
drops the tables and the column.
"""

import sqlalchemy as sa

from alembic import op

revision = "0180_application_checklists"
down_revision = "0178_offer_decisions_deposits"
branch_labels = None
depends_on = None

APPLICATIONS = "overseas_applications"
CHECKLISTS = "application_checklists"
ITEMS = "application_checklist_items"
LINKS = "application_checklist_item_documents"
MARKS = ("requested", "not_required")
GATE_MODES = ("block", "warn")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _inspect():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspect()
    columns = set() if inspector is None else {c["name"] for c in inspector.get_columns(APPLICATIONS)}
    if "documents_completed_on" not in columns:
        op.add_column(APPLICATIONS, sa.Column("documents_completed_on", sa.Date(), nullable=True))
    if inspector is not None and CHECKLISTS in inspector.get_table_names():
        return
    op.create_table(
        CHECKLISTS,
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("overseas_applications.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("template_id", sa.Uuid(), sa.ForeignKey("document_checklist_templates.id"), nullable=True),
        sa.Column("template_version", sa.Integer(), nullable=True),
        sa.Column("gate_mode", sa.String(10), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(_in("gate_mode", GATE_MODES), name="ck_application_checklists_gate_mode"),
        sa.CheckConstraint("(template_id IS NULL) = (template_version IS NULL)", name="ck_application_checklists_template_version"),
    )
    op.create_table(
        ITEMS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey(f"{CHECKLISTS}.application_id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("from_template", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("label", sa.String(80), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("allowed_statuses", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("mark", sa.String(20), nullable=True),
        sa.Column("marked_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("application_id", "position", name="uq_application_checklist_items_position"),
        sa.CheckConstraint("mark IS NULL OR " + _in("mark", MARKS), name="ck_application_checklist_items_mark"),
    )
    op.create_table(
        LINKS,
        sa.Column("item_id", sa.Uuid(), sa.ForeignKey(f"{ITEMS}.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("student_documents.id", ondelete="CASCADE"), primary_key=True, index=True),
        sa.Column("linked_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table(LINKS)
    op.drop_table(ITEMS)
    op.drop_table(CHECKLISTS)
    op.drop_column(APPLICATIONS, "documents_completed_on")
