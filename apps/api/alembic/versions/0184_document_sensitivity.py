"""ccrm-022 -- a sensitivity class on checklist template items and application checklist items.

Revision ID: 0184_document_sensitivity
Revises: 0183_offer_conditions

docs/superpowers/specs/2026-10-25-ccrm-022-sensitive-documents-design.md (DEC-SCOPE-262). Each table gets `sensitivity` (standard /
identity / financial, default standard) and its CHECK; existing items are classed from their type and label words (SD1, the
app.document_checklists word lists, repeated here and checked by test_ccrm_022_migration). 0001 builds a fresh database from the current
models, so a column is added only when missing (0166's idiom). The downgrade drops the columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0184_document_sensitivity"
down_revision = "0183_offer_conditions"
branch_labels = None
depends_on = None

TABLES = ("document_checklist_template_items", "application_checklist_items")
CLASSES = ("standard", "identity", "financial")
IDENTITY_TYPES = ("passport", "aadhaar", "aadhar", "national id", "identity", "id card", "birth certificate")
FINANCIAL_TYPES = ("financial", "finance", "bank", "sponsor", "sponsorship", "loan", "income", "salary", "tax", "itr", "affidavit")


def _words(names: tuple[str, ...]) -> str:
    """A whole-word, case-insensitive pattern (`~*`); a space in a name matches any run of non-letters, as the app's rule does."""
    return r"(^|[^a-z])(" + "|".join(sorted(n.replace(" ", "[^a-z]+") for n in names)) + r")([^a-z]|$)"


def _backfill(table: str) -> str:
    text = "(document_type || ' ' || coalesce(label, ''))"
    return f"""
UPDATE {table} SET sensitivity = CASE
    WHEN {text} ~* '{_words(FINANCIAL_TYPES)}' THEN 'financial'
    WHEN {text} ~* '{_words(IDENTITY_TYPES)}' THEN 'identity'
    ELSE 'standard' END
WHERE sensitivity = 'standard'
"""


def upgrade() -> None:
    inspector = None if op.get_context().as_sql else sa.inspect(op.get_bind())
    for table in TABLES:
        if inspector is None or "sensitivity" not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column("sensitivity", sa.String(20), nullable=False, server_default=sa.text("'standard'")))
            op.create_check_constraint(f"ck_{table}_sensitivity", table, "sensitivity IN (" + ", ".join(repr(c) for c in CLASSES) + ")")
        op.execute(_backfill(table))


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(f"ck_{table}_sensitivity", table, type_="check")
        op.drop_column(table, "sensitivity")
