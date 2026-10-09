"""rec-022 -- offer management: job_offers gains position / letter file / creator, the §16 statuses (legacy values mapped) and their CHECK;
job_offer_events.

Revision ID: 0138_offer_management
Revises: 0137_resume_search

docs/superpowers/specs/2026-10-09-rec-022-offer-management-design.md §2 (DEC-SCOPE-155). 0001 builds a fresh database from the current
models, which already carry these columns and the table, so every step is guarded. The mapping (OF10) is one-way: offered -> offer_received;
accepted, joined -> accepted; declined, rejected, withdrawn -> declined; pending -> offer_pending; any other value -> offer_received. No
history is backfilled. CHECKS repeats app.models.OFFER_CHECKS (test_rec_022_migration). downgrade() refuses while any offer history exists:
entered data is never dropped silently.

Re-chained on 2026-10-09: drafted as `0136_offer_management` (DEC-SCOPE-152, API §12BT, RBAC §2.78) on `0135_resume_extraction`. upc-011
(`0136_partnership_events`, 152), upc-018 (153) and rec-014 (`0137_resume_search`, 154) merged first, so this is `0138` (DEC-SCOPE-155,
§12BW, §2.81). A database stamped at the draft is re-stamped with `alembic stamp --purge 0135_resume_extraction`, then `upgrade head`
(every step is guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0138_offer_management"
down_revision = "0137_resume_search"
branch_labels = None
depends_on = None

TABLE, EVENTS_TABLE = "job_offers", "job_offer_events"
UUID = postgresql.UUID(as_uuid=True)
STATUSES = ("offer_pending", "offer_received", "accepted", "declined")
EVENTS = ("created", "status", "revised", "letter")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


CHECKS = {"ck_job_offers_status": f"status IN ({_in(STATUSES)})"}  # must equal app.models.OFFER_CHECKS
EVENT_CHECKS = {"ck_job_offer_events_event": f"event IN ({_in(EVENTS)})"}  # must equal app.models.OFFER_EVENT_CHECKS

MAPPING = f"""
UPDATE {TABLE} SET status = CASE
  WHEN status IN ({_in(STATUSES)}) THEN status
  WHEN status IN ('accepted', 'joined') THEN 'accepted'
  WHEN status IN ('declined', 'rejected', 'withdrawn') THEN 'declined'
  WHEN status = 'pending' THEN 'offer_pending'
  ELSE 'offer_received' END
"""
COLUMNS = ("position", "letter_key", "letter_content_type", "letter_name", "letter_uploaded_at", "created_by_user_id")


def _inspect():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspect()
    tables = set(inspector.get_table_names()) if inspector else set()
    columns = {c["name"] for c in inspector.get_columns(TABLE)} if inspector else set()
    checks = {c["name"] for c in inspector.get_check_constraints(TABLE)} if inspector else set()

    def fk(target: str):
        return sa.ForeignKey(target, ondelete="RESTRICT")

    for column in (
        sa.Column("position", sa.String(160), nullable=True),
        sa.Column("letter_key", sa.String(255), nullable=True),
        sa.Column("letter_content_type", sa.String(80), nullable=True),
        sa.Column("letter_name", sa.String(255), nullable=True),
        sa.Column("letter_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", UUID, fk("users.id"), nullable=True),
    ):
        if column.name not in columns:
            op.add_column(TABLE, column)
    for name, sql in CHECKS.items():
        if name not in checks:
            op.execute(MAPPING)
            op.alter_column(TABLE, "status", server_default=sa.text("'offer_received'"))
            op.create_check_constraint(name, TABLE, sql)
    if EVENTS_TABLE not in tables:
        op.create_table(
            EVENTS_TABLE,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("offer_id", UUID, fk(f"{TABLE}.id"), nullable=False),
            sa.Column("event", sa.String(16), nullable=False),
            sa.Column("from_status", sa.String(30), nullable=True),
            sa.Column("to_status", sa.String(30), nullable=True),
            sa.Column("fields", sa.JSON(), nullable=True),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("letter_key", sa.String(255), nullable=True),
            sa.Column("actor_user_id", UUID, fk("users.id"), nullable=True),
            sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in EVENT_CHECKS.items()),
        )
        op.create_index("ix_job_offer_events_offer", EVENTS_TABLE, ["offer_id", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {EVENTS_TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0138_offer_management: offer history exists. Clear it deliberately first.")
    op.drop_table(EVENTS_TABLE)
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    op.alter_column(TABLE, "status", server_default=None)  # the mapped statuses stay: the legacy column was free text
    for name in reversed(COLUMNS):
        op.drop_column(TABLE, name)
