"""tel-019 -- `bdm_meeting_requests` + `bdm_meeting_request_code_seq` (EVID-019 §9 BDM meeting types).

Revision ID: 0093_bdm_meeting_requests
Revises: 0091_lead_appointments

docs/superpowers/specs/2026-10-07-tel-019-bdm-meeting-requests-design.md §2 (DEC-SCOPE-097). A new table touches no existing row. 0001
builds a fresh database from the current models, which already carry the table, so the upgrade is guarded (0074's idiom). The downgrade
refuses while requests exist. tel-010 (unmerged) holds 0092: whichever of the two merges second re-chains its down_revision.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0093_bdm_meeting_requests"
down_revision = "0091_lead_appointments"
branch_labels = None
depends_on = None

TABLE = "bdm_meeting_requests"
SEQ = "bdm_meeting_request_code_seq"
# Frozen copies of the model's rules; test_tel_019_migration asserts they stay identical.
TYPES = ("college", "agent", "school", "corporate")
STATUSES = ("pending", "accepted", "declined")
MODES = ("Online", "Phone", "In person")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {
    "ck_bdm_meeting_requests_type": _in("request_type", TYPES),
    "ck_bdm_meeting_requests_bdm_type": "bdm_type IN ('agent', 'school', 'college')",
    "ck_bdm_meeting_requests_mode": _in("mode", MODES),
    "ck_bdm_meeting_requests_status": _in("status", STATUSES),
    "ck_bdm_meeting_requests_accepted": "(status = 'accepted') = (bdm_appointment_id IS NOT NULL)",
    "ck_bdm_meeting_requests_declined": "(status = 'declined') = (decline_reason IS NOT NULL)",
    "ck_bdm_meeting_requests_decided": "status = 'pending' OR (bdm_user_id IS NOT NULL AND decided_at IS NOT NULL)",
}
INDEXES = {
    "ix_bdm_meeting_requests_type_status": ["bdm_type", "status"],
    "ix_bdm_meeting_requests_bdm": ["bdm_user_id"],
    "ix_bdm_meeting_requests_requester": ["requester_user_id", "created_at"],
}


def upgrade() -> None:
    if not op.get_context().as_sql and sa.inspect(op.get_bind()).has_table(TABLE):
        return
    uuid = postgresql.UUID(as_uuid=True)
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}")
    op.create_table(
        TABLE,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("requester_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("request_type", sa.String(20), nullable=False),
        sa.Column("bdm_type", sa.String(20), nullable=False),
        sa.Column("organization_name", sa.String(200), nullable=False),
        sa.Column("person_name", sa.String(200), nullable=False),
        sa.Column("contact_phone", sa.String(30), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("purpose", sa.String(1000), nullable=False),
        sa.Column("remarks", sa.String(2000), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("bdm_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("bdm_appointment_id", uuid, sa.ForeignKey("bdm_appointments.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("decline_reason", sa.String(500), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_bdm_meeting_requests_code"),
        sa.UniqueConstraint("bdm_appointment_id", name="uq_bdm_meeting_requests_appointment"),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
    )
    for name, columns in INDEXES.items():
        op.create_index(name, TABLE, columns)


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {TABLE}")):
        raise RuntimeError("Refusing to downgrade 0093: BDM meeting requests exist and would be lost")
    op.drop_table(TABLE)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
