"""tel-016 -- `appointments` gains a lead link; `appointment_events` + `appointment_code_seq` (EVID-019 §9).

Revision ID: 0091_lead_appointments
Revises: 0090_lead_follow_ups

docs/superpowers/specs/2026-10-07-tel-016-lead-appointments-design.md §2 (DEC-SCOPE-095). Every new column is nullable (or has a server
default), so no existing row changes; legacy free-text statuses are left as stored (AP12). Every legacy row has a student (the API and the
seed require one), so the subject CHECK holds. 0001 builds a fresh database from the current models, which already carry the columns, so
the upgrade is guarded (0074's idiom). The downgrade refuses while lead appointments exist: it never orphans a lead's bookings.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0091_lead_appointments"
down_revision = "0090_lead_follow_ups"
branch_labels = None
depends_on = None

TABLE = "appointments"
EVENTS = "appointment_events"
SEQ = "appointment_code_seq"
# Frozen copies of the model's rules; test_tel_016_migration asserts they stay identical.
OPEN = ("scheduled", "confirmed", "rescheduled")
CHECKS = {"ck_appointments_subject": "student_id IS NOT NULL OR lead_id IS NOT NULL"}
OPEN_WHERE = f"lead_id IS NOT NULL AND status IN ({', '.join(repr(s) for s in OPEN)})"


def upgrade() -> None:
    if not op.get_context().as_sql and "lead_id" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}:
        return
    uuid = postgresql.UUID(as_uuid=True)
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}")
    op.add_column(TABLE, sa.Column("lead_id", uuid, sa.ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=True))
    op.add_column(TABLE, sa.Column("appointment_code", sa.String(20), nullable=True))
    op.add_column(TABLE, sa.Column("duration_minutes", sa.Integer(), server_default="60", nullable=False))
    op.add_column(TABLE, sa.Column("purpose", sa.String(500), nullable=True))
    op.add_column(TABLE, sa.Column("meeting_link", sa.String(500), nullable=True))
    op.add_column(TABLE, sa.Column("location", sa.String(200), nullable=True))
    op.add_column(TABLE, sa.Column("remarks", sa.String(1000), nullable=True))
    op.add_column(TABLE, sa.Column("booked_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True))
    op.create_unique_constraint("appointments_appointment_code_key", TABLE, ["appointment_code"])
    for name, sql in CHECKS.items():
        op.create_check_constraint(name, TABLE, sql)
    op.create_index("ix_appointments_staff_scheduled", TABLE, ["staff_id", "scheduled_at"])
    op.create_index("ix_appointments_lead", TABLE, ["lead_id"])
    op.create_index("uq_appointments_lead_open", TABLE, ["lead_id"], unique=True, postgresql_where=sa.text(OPEN_WHERE))
    op.create_table(
        EVENTS,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("appointment_id", uuid, sa.ForeignKey("appointments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("old_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_appointment_events_appointment", EVENTS, ["appointment_id", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().scalar(sa.text("SELECT count(*) FROM appointments WHERE lead_id IS NOT NULL")):
        raise RuntimeError("Refusing to downgrade 0091: lead appointments exist and would lose their lead")
    op.drop_table(EVENTS)
    op.drop_index("uq_appointments_lead_open", table_name=TABLE)
    op.drop_index("ix_appointments_lead", table_name=TABLE)
    op.drop_index("ix_appointments_staff_scheduled", table_name=TABLE)
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    op.drop_constraint("appointments_appointment_code_key", TABLE, type_="unique")
    for column in ("booked_by_user_id", "remarks", "location", "meeting_link", "purpose", "duration_minutes", "appointment_code", "lead_id"):
        op.drop_column(TABLE, column)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
