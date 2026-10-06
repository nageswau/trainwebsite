"""bdm-011 -- link appointments to trips: bdm_appointments.trip_id.

Revision ID: 0087_bdm_appointment_trip
Revises: 0086_lead_enquiries

docs/superpowers/specs/2026-10-06-bdm-011-trip-appointments-design.md §3 (DEC-SCOPE-089). Additive: one nullable column (FK to
bdm_trips, RESTRICT -- trips are never deleted) and its index; no existing row is read or written. 0001 builds a fresh database from
the current models, which already carry the column, so each step runs only when missing. downgrade() drops the links.
"""

import sqlalchemy as sa

from alembic import op

revision = "0087_bdm_appointment_trip"
down_revision = "0086_lead_enquiries"
branch_labels = None
depends_on = None

TABLE = "bdm_appointments"
FK = "fk_bdm_appointments_trip_id"
INDEX = "ix_bdm_appointments_trip"


def upgrade() -> None:
    columns: set[str] = set()
    indexes: set[str | None] = set()
    if not op.get_context().as_sql:  # offline SQL has no database to inspect: emit every step
        insp = sa.inspect(op.get_bind())
        columns = {c["name"] for c in insp.get_columns(TABLE)}
        indexes = {i["name"] for i in insp.get_indexes(TABLE)}
    if "trip_id" not in columns:
        op.add_column(TABLE, sa.Column("trip_id", sa.Uuid(), nullable=True))
        op.create_foreign_key(FK, TABLE, "bdm_trips", ["trip_id"], ["id"], ondelete="RESTRICT")
    if INDEX not in indexes:
        op.create_index(INDEX, TABLE, ["trip_id"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_column(TABLE, "trip_id")  # drops the FK with it
