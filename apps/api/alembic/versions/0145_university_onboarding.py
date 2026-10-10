"""upc-027 -- university_onboarding_items: the §29 partner onboarding checklist.

Revision ID: 0145_university_onboarding
Revises: 0144_commission_receipts

docs/superpowers/specs/2026-10-10-upc-027-partner-onboarding-design.md §2 (DEC-SCOPE-169). A new table only; no existing row changes.
Rows are sparse (OB2: the catalogue is the template), so there is no backfill. 0001 builds a fresh database from the current models,
which already carry the table, so it is created only when missing (0117's idiom). KINDS / STATUSES / CHECKS repeat app.models
(test_upc_027_migration). downgrade() refuses while any row exists: it would drop recorded onboarding progress.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0145_university_onboarding"
down_revision = "0144_commission_receipts"
branch_labels = None
depends_on = None

TABLE = "university_onboarding_items"
UUID = postgresql.UUID(as_uuid=True)
KINDS = (
    "counselor_training", "application_team_training", "product_training", "university_portal_access", "application_process",
    "marketing_material", "course_database_updated", "commission_setup", "university_contact_setup", "first_student_campaign",
)  # fmt: skip
STATUSES = ("not_started", "in_progress", "completed")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {  # must equal app.models.UNIVERSITY_ONBOARDING_CHECKS
    "ck_university_onboarding_items_kind": _in("kind", KINDS),
    "ck_university_onboarding_items_status": _in("status", STATUSES),
    "ck_university_onboarding_items_completed": "(status = 'completed') = (completed_on IS NOT NULL)",
    "ck_university_onboarding_items_note": "note IS NULL OR char_length(note) <= 500",
}


def fk(target: str):
    return sa.ForeignKey(target, ondelete="RESTRICT")


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("university_id", UUID, fk("universities.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'not_started'"), nullable=False),
        sa.Column("owner_user_id", UUID, fk("users.id"), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("completed_on", sa.Date(), nullable=True),
        sa.Column("updated_by_user_id", UUID, fk("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        sa.UniqueConstraint("university_id", "kind", name="uq_university_onboarding_items_kind"),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0145_university_onboarding: onboarding progress exists. Remove it deliberately first.")
    op.drop_table(TABLE)
