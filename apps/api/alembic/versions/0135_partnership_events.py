"""upc-011 -- Partnership events (the §9 calendar's conferences, fairs, webinars, ...).

Revision ID: 0135_partnership_events
Revises: 0134_application_screenings

docs/superpowers/specs/2026-10-09-upc-011-partnership-calendar-design.md §2 (DEC-SCOPE-150). Adds `partnership_event_code_seq`,
`partnership_events` and `partnership_event_participants`. New tables only; no existing row changes. 0001 builds a fresh database from
the current models, which already carry them, so the table step is guarded. CHECKS repeats app.models (test_upc_011_migration).
downgrade() refuses while any event exists: entered data is never dropped silently.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0135_partnership_events"
down_revision = "0134_application_screenings"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
KINDS = "'conference', 'education_fair', 'partner_meeting', 'mou_signing', 'webinar', 'university_presentation'"
CHECKS = {
    "ck_partnership_events_kind": f"kind IN ({KINDS})",
    "ck_partnership_events_status": "status IN ('scheduled', 'cancelled')",
    "ck_partnership_events_dates": "ends_on >= starts_on",
    "ck_partnership_events_cancelled": "(status = 'cancelled') = (cancelled_at IS NOT NULL) AND (cancelled_at IS NULL) = (cancel_reason IS NULL)",
}


def _user_fk(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


def _timestamp(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS partnership_event_code_seq")
    if not op.get_context().as_sql and "partnership_events" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "partnership_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("university_id", UUID, sa.ForeignKey("universities.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        _user_fk("owner_user_id"),
        _user_fk("created_by_user_id"),
        sa.Column("status", sa.String(12), nullable=False, server_default="scheduled"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.UniqueConstraint("code", name="uq_partnership_events_code"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    op.create_index("ix_partnership_events_dates", "partnership_events", ["starts_on", "ends_on"])
    op.create_index("ix_partnership_events_owner", "partnership_events", ["owner_user_id"])
    op.create_index("ix_partnership_events_university", "partnership_events", ["university_id"])
    op.create_table(
        "partnership_event_participants",
        sa.Column("event_id", UUID, sa.ForeignKey("partnership_events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM partnership_events LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0135_partnership_events: partnership events exist. Remove them deliberately first.")
    op.drop_table("partnership_event_participants")
    op.drop_table("partnership_events")
    op.execute("DROP SEQUENCE IF EXISTS partnership_event_code_seq")
