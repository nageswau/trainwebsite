"""ccrm-026 -- the visa case lifecycle: visa_cases.visa_status (Appendix A, CHECK) with its backfill, and the lifecycle columns.

Revision ID: 0177_visa_lifecycle
Revises: 0176_document_status

docs/superpowers/specs/2026-10-24-ccrm-026-visa-lifecycle-design.md (DEC-SCOPE-252). Backfill: the recorded decision if any, else the
stage's first status (FIRST_OF_STAGE); a stage outside the list (the seed's legacy `not_started`) -> not_started. decision_date comes
from decided_at. 0001 builds a fresh database from the current models, which already carry the columns, so each step runs only when
missing (0166's idiom). STATUSES / FIRST_OF_STAGE repeat app.visa_status (test_ccrm_026_migration). The downgrade drops the columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0177_visa_lifecycle"
down_revision = "0176_document_status"
branch_labels = None
depends_on = None

TABLE = "visa_cases"
STATUSES = ("not_started", "preparing", "appointment_booked", "submitted", "additional_info_requested", "decision_pending", "approved", "refused", "withdrawn")
FIRST_OF_STAGE = {"checklist": "not_started", "documentation": "preparing", "interview_prep": "appointment_booked", "tracking": "submitted", "decision": "decision_pending"}
STATUS_CHECK = "ck_visa_cases_visa_status"
COLUMNS = (
    ("readiness_review_date", sa.Date()),
    ("visa_category", sa.String(80)),
    ("appointment_place", sa.String(200)),
    ("expected_decision_date", sa.Date()),
    ("decision_date", sa.Date()),
    ("refusal_reason", sa.Text()),
    ("next_steps", sa.Text()),
)


def _in(values) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _columns() -> set[str]:
    return set() if op.get_context().as_sql else {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    existing = _columns()
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True))
    if "outcome_document_id" not in existing:
        op.add_column(TABLE, sa.Column("outcome_document_id", sa.Uuid(), sa.ForeignKey("student_documents.id", ondelete="SET NULL"), nullable=True))
    if "visa_status" in existing:
        return
    op.add_column(TABLE, sa.Column("visa_status", sa.String(40), nullable=False, server_default="not_started"))
    stage_map = " ".join(f"WHEN '{stage}' THEN '{status}'" for stage, status in FIRST_OF_STAGE.items())
    op.execute(f"UPDATE {TABLE} SET visa_status = COALESCE(decision, CASE status {stage_map} ELSE 'not_started' END)")  # noqa: S608 -- constants
    op.execute(f"UPDATE {TABLE} SET decision_date = (decided_at AT TIME ZONE 'Asia/Kolkata')::date WHERE decided_at IS NOT NULL")
    op.create_check_constraint(STATUS_CHECK, TABLE, f"visa_status IN {_in(STATUSES)}")


def downgrade() -> None:
    op.drop_constraint(STATUS_CHECK, TABLE, type_="check")
    for name in ("visa_status", "outcome_document_id", *(name for name, _ in COLUMNS)):
        op.drop_column(TABLE, name)
