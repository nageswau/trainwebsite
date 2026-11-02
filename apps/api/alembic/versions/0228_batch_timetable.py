"""itc-020 -- batch timetable: weekly slots and single-class cancellations.

Revision ID: 0228_batch_timetable
Revises: 0227_lead_counseling_records

docs/superpowers/specs/2026-11-02-itc-020-batch-timetable-design.md (DEC-SCOPE-344). Two new tables; nothing existing changes (the free
text `batches.schedule` stays). 0001 builds a fresh database from the current models, which already carry them, so the upgrade is guarded
(0222's idiom). The downgrade refuses while a timetable exists, so it never silently drops one.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0228_batch_timetable"
down_revision = "0227_lead_counseling_records"
branch_labels = None
depends_on = None

SLOTS = "batch_timetable_slots"
CANCELLATIONS = "batch_timetable_cancellations"
UUID = postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    if not op.get_context().as_sql and SLOTS in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        SLOTS,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("batch_id", UUID, sa.ForeignKey("batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.SmallInteger, nullable=False),
        sa.Column("start_time", sa.Time, nullable=False),
        sa.Column("end_time", sa.Time, nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("room", sa.String(120), nullable=True),
        sa.Column("meeting_url", sa.String(500), nullable=True),
        sa.Column("topic", sa.String(160), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_batch_timetable_slots_weekday"),
        sa.CheckConstraint("end_time > start_time", name="ck_batch_timetable_slots_times"),
        sa.CheckConstraint("mode IN ('online', 'offline')", name="ck_batch_timetable_slots_mode"),
        sa.CheckConstraint("mode = 'online' OR room IS NOT NULL", name="ck_batch_timetable_slots_room"),
    )
    op.create_index("ix_batch_timetable_slots_batch_id", SLOTS, ["batch_id"])
    op.create_table(
        CANCELLATIONS,
        sa.Column("id", UUID, primary_key=True),
        sa.Column("slot_id", UUID, sa.ForeignKey(f"{SLOTS}.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurs_on", sa.Date, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("cancelled_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("slot_id", "occurs_on", name="uq_batch_timetable_cancellations_slot_day"),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {SLOTS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0228: batch timetables exist (itc-020)")
    op.drop_table(CANCELLATIONS)
    op.drop_index("ix_batch_timetable_slots_batch_id", table_name=SLOTS)
    op.drop_table(SLOTS)
