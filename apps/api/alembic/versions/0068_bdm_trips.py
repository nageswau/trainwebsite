"""bdm-010 -- bdm_trips, bdm_trip_expenses and the bdm_trip_code_seq sequence.

Revision ID: 0068_bdm_trips
Revises: 0067_audit_entity_index

docs/superpowers/specs/2026-10-03-bdm-010-travel-design.md §4 (DEC-SCOPE-063). Additive: two tables and one sequence; no existing
row is read or written. 0001 builds a fresh database from the current models, which already carry all three, so creation is
guarded (0061's idiom). downgrade() refuses while trips exist: they are the only record of each trip's approval and costs.

Re-chained 2026-10-03 on merging `main` @ `3bde879`: cut as `0066_bdm_trips` on `0065_agent_notifications` (DEC-SCOPE-060), but
bdm-002's `0066_bdm_organizations` (DEC-SCOPE-060) and AGN-015's `0067_audit_entity_index` (DEC-SCOPE-061) reached `main` first, and
AGN-018 took DEC-SCOPE-062; this revision is now `0068_bdm_trips` after 0067 (one head) and the decision is DEC-SCOPE-063. A database
stamped at `0066_bdm_trips` is re-stamped with `alembic stamp --purge 0065_agent_notifications` then `upgrade head` (every create
here is guarded, so the re-run is harmless).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0068_bdm_trips"
down_revision = "0067_audit_entity_index"
branch_labels = None
depends_on = None

TRIPS, EXPENSES, SEQUENCE = "bdm_trips", "bdm_trip_expenses", "bdm_trip_code_seq"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE}")
    if not op.get_context().as_sql and TRIPS in sa.inspect(op.get_bind()).get_table_names():
        return
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        TRIPS,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("bdm_user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("travel_date", sa.Date(), nullable=False),
        sa.Column("return_date", sa.Date(), nullable=False),
        sa.Column("from_place", sa.String(120), nullable=False),
        sa.Column("to_place", sa.String(120), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("accommodation_required", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("approval_status", sa.String(12), server_default="draft", nullable=False),
        sa.Column("travel_status", sa.String(12), server_default="planned", nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("decided_by_user_id", uuid, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_bdm_trips_code"),
        sa.CheckConstraint("return_date >= travel_date", name="ck_bdm_trips_dates"),
        sa.CheckConstraint("mode IN ('flight', 'train', 'bus', 'car', 'cab', 'local')", name="ck_bdm_trips_mode"),
        sa.CheckConstraint("estimated_cost >= 0", name="ck_bdm_trips_estimated_cost"),
        sa.CheckConstraint("currency = 'INR'", name="ck_bdm_trips_currency"),
        sa.CheckConstraint("approval_status IN ('draft', 'submitted', 'approved', 'rejected')", name="ck_bdm_trips_approval_status"),
        sa.CheckConstraint("travel_status IN ('planned', 'in_progress', 'completed', 'cancelled')", name="ck_bdm_trips_travel_status"),
        sa.CheckConstraint("travel_status IN ('planned', 'cancelled') OR approval_status = 'approved'", name="ck_bdm_trips_status_pair"),
    )
    op.create_index("ix_bdm_trips_bdm_travel_date", TRIPS, ["bdm_user_id", "travel_date"])
    op.create_index("ix_bdm_trips_submitted", TRIPS, ["bdm_user_id"], postgresql_where=sa.text("approval_status = 'submitted'"))
    op.create_table(
        EXPENSES,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("trip_id", uuid, sa.ForeignKey("bdm_trips.id"), nullable=False),
        sa.Column("category", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_by_user_id", uuid, sa.ForeignKey("users.id"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("category IN ('travel', 'stay', 'food', 'local', 'other')", name="ck_bdm_trip_expenses_category"),
        sa.CheckConstraint("amount > 0", name="ck_bdm_trip_expenses_amount"),
    )
    op.create_index("ix_bdm_trip_expenses_trip", EXPENSES, ["trip_id"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TRIPS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0068_bdm_trips: BDM trips exist. Remove them deliberately first.")
    op.drop_table(EXPENSES)
    # bdm-011: a database 0001 built from newer models already has bdm_appointments.trip_id -> bdm_trips (the real chain drops it in
    # 0085's downgrade). With no trip left (checked above) every link is NULL, so dropping the column loses nothing.
    op.execute("ALTER TABLE IF EXISTS bdm_appointments DROP COLUMN IF EXISTS trip_id")
    op.drop_table(TRIPS)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQUENCE}")
