"""upc-010 -- University visits + approval.

Revision ID: 0111_university_visits
Revises: 0110_company_contacts

docs/superpowers/specs/2026-10-08-upc-010-university-visits-design.md §2 (DEC-SCOPE-126). Adds `university_visit_code_seq`,
`university_visits`, its participants and contacts, and the append-only `university_visit_events`. 0001 builds a fresh database from
the current models, which already carry all of this, so each step is guarded. STATUS_CHECK repeats app.models (test_upc_010_migration).
downgrade() refuses while any visit exists: it would drop visit plans, approvals and their history.

Re-chained 2026-10-08: drafted as `0109_university_visits` on `0108_university_contacts` (DEC-SCOPE-124, API §12AR, RBAC §2.50), but
upc-004's `0109_university_duplicates` and rec-004's `0110_company_contacts` merged first (main @ `4043631f`), so this is `0111`
(DEC-SCOPE-126, API §12AT, RBAC §2.52). A database stamped at `0109_university_visits` is re-stamped with `alembic stamp --purge
0108_university_contacts`, then `upgrade head` (every step here is guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0111_university_visits"
down_revision = "0110_company_contacts"
branch_labels = None
depends_on = None

STATUS_CHECK = "status IN ('planned', 'approved', 'travel_booked', 'visit_completed', 'follow_up', 'closed')"
UUID = postgresql.UUID(as_uuid=True)


def _user_fk(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS university_visit_code_seq")
    tables = set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())  # offline SQL: emit everything
    if "university_visits" not in tables:
        op.create_table(
            "university_visits",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("code", sa.String(20), nullable=False),
            sa.Column("university_id", UUID, sa.ForeignKey("universities.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("city", sa.String(120), nullable=False),
            sa.Column("purpose", sa.Text(), nullable=False),
            _user_fk("lead_user_id"),
            _user_fk("created_by_user_id"),
            sa.Column("proposed_date", sa.Date(), nullable=False),
            sa.Column("confirmed_date", sa.Date(), nullable=True),
            sa.Column("travel_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("travel_notes", sa.Text(), nullable=True),
            sa.Column("hotel_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("hotel_notes", sa.Text(), nullable=True),
            sa.Column("agenda", sa.Text(), nullable=True),
            sa.Column("expected_outcome", sa.Text(), nullable=True),
            sa.Column("follow_up_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="planned"),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            _user_fk("decided_by_user_id", nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("close_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("code", name="uq_university_visits_code"),
            sa.CheckConstraint(STATUS_CHECK, name="ck_university_visits_status"),
        )
        op.create_index("ix_university_visits_university", "university_visits", ["university_id"])
        op.create_index("ix_university_visits_lead", "university_visits", ["lead_user_id"])
        op.create_index("ix_university_visits_pending", "university_visits", ["submitted_at"], postgresql_where=sa.text("status = 'planned' AND submitted_at IS NOT NULL"))
    if "university_visit_participants" not in tables:
        op.create_table(
            "university_visit_participants",
            sa.Column("visit_id", UUID, sa.ForeignKey("university_visits.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        )
    if "university_visit_contacts" not in tables:
        op.create_table(
            "university_visit_contacts",
            sa.Column("visit_id", UUID, sa.ForeignKey("university_visits.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("contact_id", UUID, sa.ForeignKey("university_contacts.id", ondelete="CASCADE"), primary_key=True),
        )
    if "university_visit_events" not in tables:
        op.create_table(
            "university_visit_events",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("visit_id", UUID, sa.ForeignKey("university_visits.id", ondelete="CASCADE"), nullable=False),
            sa.Column("action", sa.String(20), nullable=False),
            sa.Column("from_status", sa.String(16), nullable=True),
            sa.Column("to_status", sa.String(16), nullable=True),
            _user_fk("actor_user_id"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_university_visit_events_visit", "university_visit_events", ["visit_id", "created_at"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text("SELECT 1 FROM university_visits LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0111_university_visits: visits exist. Remove them deliberately first.")
    op.drop_table("university_visit_events")
    op.drop_table("university_visit_contacts")
    op.drop_table("university_visit_participants")
    op.drop_table("university_visits")
    op.execute("DROP SEQUENCE IF EXISTS university_visit_code_seq")
