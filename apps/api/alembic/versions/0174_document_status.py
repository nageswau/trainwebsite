"""ccrm-021 -- document status list, expiry and versions: student_documents CHECK + data map, expiry_date, reviewed_at, archived_at,
version_of_id; the widened document_events CHECK.

Revision ID: 0174_document_status
Revises: 0173_checklist_templates

docs/superpowers/specs/2026-10-24-ccrm-021-document-status-design.md (DEC-SCOPE-249). S1 data map: rejected -> reupload_required,
changes_required -> incomplete, any other value outside STATUSES -> under_review; `pending` stays. reviewed_at is backfilled from the
latest review event. 0001 builds a fresh database from the current models, which already carry the columns and constraints, so each
step runs only when missing (0166's idiom). STATUSES / EVENTS repeat app.document_checklists.ITEM_STATUSES and
app.models.DOCUMENT_EVENTS (test_ccrm_021_migration). The downgrade maps the new codes back (lossy: codes with no old value -> pending).
"""

import sqlalchemy as sa

from alembic import op

revision = "0174_document_status"
down_revision = "0173_checklist_templates"
branch_labels = None
depends_on = None

TABLE = "student_documents"
STATUSES = ("pending", "requested", "uploaded", "under_review", "verified", "incomplete", "reupload_required", "expired", "not_required", "draft", "review", "approved")
LEGACY = {"rejected": "reupload_required", "changes_required": "incomplete"}
OLD_EVENTS = ("uploaded", "replaced", "verified", "rejected", "changes_required", "requested", "fulfilled", "cancelled", "downloaded")
EVENTS = OLD_EVENTS + ("under_review", "incomplete", "reupload_required", "expired", "not_required", "draft", "review", "approved")
REVIEW_EVENTS = ("verified", "rejected", "changes_required")
STATUS_CHECK, EVENT_CHECK, EXPIRY_INDEX = "ck_student_documents_status", "ck_document_events_event", "ix_student_documents_expiry"


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _has_column(name: str) -> bool:
    return not op.get_context().as_sql and name in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def _has_check(table: str, name: str) -> bool:
    return not op.get_context().as_sql and name in {c["name"] for c in sa.inspect(op.get_bind()).get_check_constraints(table)}


def upgrade() -> None:
    for column in (
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version_of_id", sa.Uuid(), sa.ForeignKey(f"{TABLE}.id"), nullable=True),
    ):
        if not _has_column(column.name):
            op.add_column(TABLE, column)
    for old, new in LEGACY.items():
        op.execute(f"UPDATE {TABLE} SET verification_status = '{new}' WHERE verification_status = '{old}'")
    op.execute(f"UPDATE {TABLE} SET verification_status = 'under_review' WHERE verification_status NOT IN {_in(STATUSES)}")
    op.execute(
        f"UPDATE {TABLE} d SET reviewed_at = e.at FROM (SELECT document_id, max(created_at) AS at FROM document_events "
        f"WHERE event IN {_in(REVIEW_EVENTS)} GROUP BY document_id) e WHERE e.document_id = d.id AND d.reviewed_at IS NULL"
    )
    if not _has_check(TABLE, STATUS_CHECK):
        op.create_check_constraint(STATUS_CHECK, TABLE, f"verification_status IN {_in(STATUSES)}")
    op.execute(f"ALTER TABLE document_events DROP CONSTRAINT IF EXISTS {EVENT_CHECK}")
    op.create_check_constraint(EVENT_CHECK, "document_events", f"event IN {_in(EVENTS)}")
    op.execute(f"CREATE INDEX IF NOT EXISTS {EXPIRY_INDEX} ON {TABLE} (expiry_date) WHERE archived_at IS NULL AND expiry_date IS NOT NULL")


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {EXPIRY_INDEX}")
    for old, new in LEGACY.items():
        op.execute(f"UPDATE document_events SET event = '{old}' WHERE event = '{new}'")
    op.execute(f"DELETE FROM document_events WHERE event NOT IN {_in(OLD_EVENTS)}")
    op.execute(f"ALTER TABLE document_events DROP CONSTRAINT IF EXISTS {EVENT_CHECK}")
    op.create_check_constraint(EVENT_CHECK, "document_events", f"event IN {_in(OLD_EVENTS)}")
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {STATUS_CHECK}")
    for old, new in LEGACY.items():
        op.execute(f"UPDATE {TABLE} SET verification_status = '{old}' WHERE verification_status = '{new}'")
    op.execute(f"UPDATE {TABLE} SET verification_status = 'pending' WHERE verification_status NOT IN ('pending', 'verified', 'rejected', 'changes_required')")
    for name in ("version_of_id", "archived_at", "reviewed_at", "expiry_date"):
        op.drop_column(TABLE, name)
