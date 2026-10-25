"""ccrm-027 -- enrolment confirmation: overseas_applications.enrollment_document_id / pre_enrollment_checklist_complete, and the
non_arrival / cancelled outcomes in the three outcome CHECKs.

Revision ID: 0181_enrollment_confirmation
Revises: 0180_application_checklists

docs/superpowers/specs/2026-10-25-ccrm-027-enrolment-confirmation-design.md (DEC-SCOPE-259). Additive: existing rows keep a NULL document
and `false`; nothing is backfilled (E4: an old unconfirmed enrolment stays unconfirmed). 0001 builds a fresh database from the current
models, which already carry the columns, so they are added only when missing (0170's idiom); the CHECKs are always recreated. OUTCOMES /
CLEARED repeat app.application_outcome (test_ccrm_027_migration). downgrade() restores the ccrm-015 values and drops the columns (it
fails while a row still holds a new outcome, rather than discarding it).
"""

import sqlalchemy as sa

from alembic import op

revision = "0181_enrollment_confirmation"
down_revision = "0180_application_checklists"
branch_labels = None
depends_on = None

TABLE = "overseas_applications"
FK = "fk_overseas_applications_enrollment_document_id"
OUTCOMES = ("rejected", "withdrawn", "deferred", "on_hold", "offer_declined", "visa_refused", "non_arrival", "cancelled")
PREVIOUS = OUTCOMES[:6]  # ccrm-015's values (0170 / 0172)
CLEARED = "cleared"
# (constraint, table, whether the event value 'cleared' is allowed)
CHECKS = (
    ("ck_overseas_applications_outcome", TABLE, False),
    ("ck_application_outcomes_outcome", "application_outcomes", True),
    ("ck_application_status_history_outcome", "application_status_history", True),
)


def _in(values: tuple[str, ...]) -> str:
    return f"outcome IS NULL OR outcome IN ({', '.join(repr(v) for v in values)})"


def _recreate(values: tuple[str, ...]) -> None:
    for name, table, cleared in CHECKS:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _in((*values, CLEARED) if cleared else values))


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if inspector is None or "enrollment_document_id" not in {c["name"] for c in inspector.get_columns(TABLE)}:
        op.add_column(TABLE, sa.Column("enrollment_document_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(FK, TABLE, "student_documents", ["enrollment_document_id"], ["id"], ondelete="SET NULL")
        op.add_column(TABLE, sa.Column("pre_enrollment_checklist_complete", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    _recreate(OUTCOMES)


def downgrade() -> None:
    _recreate(PREVIOUS)
    op.drop_column(TABLE, "pre_enrollment_checklist_complete")
    op.drop_constraint(FK, TABLE, type_="foreignkey")
    op.drop_column(TABLE, "enrollment_document_id")
