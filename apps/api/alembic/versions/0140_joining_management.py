"""rec-023 -- joining management: job_offers gains the EVID-018 §17 joining columns and their CHECKs; job_offer_events gains the joining events.

Revision ID: 0140_joining_management
Revises: 0139_recruiter_contracts

docs/superpowers/specs/2026-10-09-rec-023-joining-management-design.md §2 (DEC-SCOPE-158). 0001 builds a fresh database from the current
models, which already carry these columns and CHECKs, so every step is guarded. The event CHECK is re-created with the longer list. Backfill
(JN2/JN9): an Accepted offer whose application is Joined (the legacy accepted -> hired path) is `joined`; any other Accepted offer is
`pending`. No history is backfilled. CHECKS repeats app.models.JOINING_CHECKS (test_rec_023_migration). downgrade() refuses while any
joining data or joining event exists: entered data is never dropped silently.
"""

import sqlalchemy as sa

from alembic import op

revision = "0140_joining_management"
down_revision = "0139_recruiter_contracts"
branch_labels = None
depends_on = None

TABLE, EVENTS_TABLE = "job_offers", "job_offer_events"
STATUSES = ("pending", "joined", "did_not_join")
OFFER_EVENTS_0138 = ("created", "status", "revised", "letter")
EVENTS = (*OFFER_EVENTS_0138, "joining", "joined", "did_not_join", "proof")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


CHECKS = {  # must equal app.models.JOINING_CHECKS
    "ck_job_offers_joining_status": f"joining_status IS NULL OR joining_status IN ({_in(STATUSES)})",
    "ck_job_offers_not_joined_reason": "joining_status IS DISTINCT FROM 'did_not_join' OR not_joined_reason IS NOT NULL",
}
EVENT_CHECK = "ck_job_offer_events_event"
EVENT_CHECKS = {EVENT_CHECK: f"event IN ({_in(EVENTS)})"}  # must equal app.models.OFFER_EVENT_CHECKS
COLUMNS = (
    "joining_status",
    "actual_joining_date",
    "joining_location",
    "reporting_manager",
    "joining_confirmed_by",
    "joining_confirmed_on",
    "not_joined_reason",
    "proof_key",
    "proof_content_type",
    "proof_name",
    "proof_uploaded_at",
)
BACKFILL = f"""
UPDATE {TABLE} o SET joining_status = CASE WHEN a.status = 'joined' THEN 'joined' ELSE 'pending' END
FROM job_applications a WHERE a.id = o.application_id AND o.status = 'accepted' AND o.joining_status IS NULL
"""


def _inspect():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def _replace_event_check(events: tuple[str, ...]) -> None:
    op.execute(f"ALTER TABLE {EVENTS_TABLE} DROP CONSTRAINT IF EXISTS {EVENT_CHECK}")
    op.create_check_constraint(EVENT_CHECK, EVENTS_TABLE, f"event IN ({_in(events)})")


def upgrade() -> None:
    inspector = _inspect()
    columns = {c["name"] for c in inspector.get_columns(TABLE)} if inspector else set()
    checks = {c["name"] for c in inspector.get_check_constraints(TABLE)} if inspector else set()
    for column in (
        sa.Column("joining_status", sa.String(16), nullable=True),
        sa.Column("actual_joining_date", sa.Date(), nullable=True),
        sa.Column("joining_location", sa.String(160), nullable=True),
        sa.Column("reporting_manager", sa.String(160), nullable=True),
        sa.Column("joining_confirmed_by", sa.String(160), nullable=True),
        sa.Column("joining_confirmed_on", sa.Date(), nullable=True),
        sa.Column("not_joined_reason", sa.String(500), nullable=True),
        sa.Column("proof_key", sa.String(255), nullable=True),
        sa.Column("proof_content_type", sa.String(80), nullable=True),
        sa.Column("proof_name", sa.String(255), nullable=True),
        sa.Column("proof_uploaded_at", sa.DateTime(timezone=True), nullable=True),
    ):
        if column.name not in columns:
            op.add_column(TABLE, column)
    op.execute(BACKFILL)
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)
    _replace_event_check(EVENTS)


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        data = bind.execute(
            sa.text(
                f"SELECT 1 FROM {TABLE} WHERE actual_joining_date IS NOT NULL OR joining_location IS NOT NULL OR reporting_manager IS NOT NULL "
                f"OR joining_confirmed_by IS NOT NULL OR not_joined_reason IS NOT NULL OR proof_key IS NOT NULL LIMIT 1"
            )
        ).first()
        events = bind.execute(sa.text(f"SELECT 1 FROM {EVENTS_TABLE} WHERE event NOT IN ({_in(OFFER_EVENTS_0138)}) LIMIT 1")).first()
        if data or events:
            raise RuntimeError("Cannot downgrade 0140_joining_management: joining data exists. Clear it deliberately first.")
    _replace_event_check(OFFER_EVENTS_0138)
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    for name in reversed(COLUMNS):
        op.drop_column(TABLE, name)
