"""ccrm-018 -- document checklist templates and their items.

Revision ID: 0173_checklist_templates
Revises: 0172_status_history_reason

docs/superpowers/specs/2026-10-23-ccrm-018-document-checklist-templates-design.md (DEC-SCOPE-248). New tables only; nothing is seeded
(spec §8: templates must not look universal). 0001 builds a fresh database from the current models, which already carry the tables, so
they are created only when missing (0166's idiom). The scope index treats NULLs as equal and the intake case-insensitively, over active
rows only (PostgreSQL 15+). KINDS / GATE_MODES / LEVELS repeat app.document_checklists and app.models.COURSE_LEVELS
(test_ccrm_018_migration).
"""

import sqlalchemy as sa

from alembic import op

revision = "0173_checklist_templates"
down_revision = "0172_status_history_reason"
branch_labels = None
depends_on = None

TABLE = "document_checklist_templates"
ITEMS = "document_checklist_template_items"
KINDS = ("admission", "visa")
GATE_MODES = ("block", "warn")
LEVELS = ("UG", "PG", "PhD", "Diploma", "Foundation")
SCOPE_INDEX = (
    f"CREATE UNIQUE INDEX uq_document_checklist_templates_scope ON {TABLE} (kind, country_id, university_id, course_level, lower(intake)) "
    "NULLS NOT DISTINCT WHERE active"
)


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _missing() -> bool:
    return op.get_context().as_sql or TABLE not in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _missing():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("country_id", sa.Uuid(), sa.ForeignKey("countries.id"), nullable=False),
        sa.Column("university_id", sa.Uuid(), sa.ForeignKey("universities.id"), nullable=True),
        sa.Column("course_level", sa.String(20), nullable=True),
        sa.Column("intake", sa.String(80), nullable=True),
        sa.Column("gate_mode", sa.String(10), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"kind IN {_in(KINDS)}", name="ck_document_checklist_templates_kind"),
        sa.CheckConstraint(f"gate_mode IN {_in(GATE_MODES)}", name="ck_document_checklist_templates_gate_mode"),
        sa.CheckConstraint(f"course_level IS NULL OR course_level IN {_in(LEVELS)}", name="ck_document_checklist_templates_course_level"),
    )
    op.execute(SCOPE_INDEX)
    op.create_table(
        ITEMS,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("template_id", sa.Uuid(), sa.ForeignKey(f"{TABLE}.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("label", sa.String(80), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("allowed_statuses", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("template_id", "position", name="uq_document_checklist_template_items_position"),
    )


def downgrade() -> None:
    op.drop_table(ITEMS)
    op.drop_table(TABLE)
