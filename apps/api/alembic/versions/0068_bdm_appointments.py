"""bdm-006 -- bdm_appointments + bdm_appointment_events + bdm_appointment_code_seq.

Revision ID: 0068_bdm_appointments
Revises: 0067_audit_entity_index

docs/superpowers/specs/2026-10-03-bdm-006-appointments-design.md §4 (DEC-SCOPE-063). Adds two tables and one sequence; no existing
row is read or written. 0001 builds a fresh database from the current models (which carry both tables and the sequence), so creation
is guarded (0061/0066's idiom) and the sequence is created IF NOT EXISTS. downgrade() refuses while appointments exist: they are the
only record of each meeting and its history.

If another migration reaches `main` first, re-chain this revision after it (rename the file and revision, update down_revision) as
0066 did; a database stamped at the old id is re-stamped with `alembic stamp --purge <previous head>` then `upgrade head`.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0068_bdm_appointments"
down_revision = "0067_audit_entity_index"
branch_labels = None
depends_on = None

APPTS = "bdm_appointments"
EVENTS = "bdm_appointment_events"
SEQ = "bdm_appointment_code_seq"

# Inlined, not imported from app.models: a migration must not change meaning when app code changes (0066's style).
# tests/test_bdm_006_migration.py asserts these equal the model tuples.
STATUSES = ("scheduled", "confirmed", "rescheduled", "completed", "cancelled", "no_show")
ALL_TYPES = (
    "college_meeting", "agent_meeting", "school_meeting", "mou_discussion", "student_institution_meeting", "seminar_workshop",
    "corporate_meeting", "other", "new_agent_presentation", "product_training", "agreement_discussion", "performance_review",
    "agent_onboarding", "agent_visit", "commission_discussion", "business_review", "principal_meeting", "management_meeting",
    "career_guidance_presentation", "psychometric_presentation", "profile_building_presentation", "parent_orientation",
    "teacher_orientation", "seminar", "workshop", "renewal_meeting", "hod_meeting", "placement_cell_meeting", "course_promotion",
    "it_training_presentation", "student_seminar", "internship_discussion", "placement_discussion", "corporate_connect",
    "faculty_meeting",
)
ALL_OUTCOMES = (
    "interested", "mou_discussion_required", "student_leads_expected", "course_promotion_interested", "follow_up_required",
    "commercial_discussion", "not_interested", "reschedule", "other", "agreement_required", "product_training_required", "follow_up",
    "documents_required", "onboarding_required", "active_business_expected",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid(name: str, *args, nullable: bool = False, **kwargs) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, nullable=nullable, **kwargs)


def upgrade() -> None:
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}")
    if not op.get_context().as_sql and APPTS in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        APPTS,
        _uuid("id", primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        _uuid("bdm_user_id", sa.ForeignKey("users.id", ondelete="RESTRICT")),
        _uuid("organization_id", sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT")),
        _uuid("contact_id", sa.ForeignKey("bdm_organization_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_name", sa.String(200), nullable=False),
        sa.Column("contact_designation", sa.String(120), nullable=True),
        sa.Column("contact_phone", sa.String(30), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), server_default=sa.text("60"), nullable=False),
        sa.Column("appointment_type", sa.String(40), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("purpose", sa.String(1000), nullable=True),
        sa.Column("remarks", sa.String(2000), nullable=True),
        sa.Column("status", sa.String(20), server_default=sa.text("'scheduled'"), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=True),
        sa.Column("next_follow_up_on", sa.Date(), nullable=True),
        sa.Column("expected_leads", sa.Integer(), nullable=True),
        sa.Column("expected_revenue", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_bdm_appointments_code"),
        sa.CheckConstraint(_in("status", STATUSES), name="ck_bdm_appointments_status"),
        sa.CheckConstraint(_in("appointment_type", ALL_TYPES), name="ck_bdm_appointments_type"),
        sa.CheckConstraint(f"outcome IS NULL OR {_in('outcome', ALL_OUTCOMES)}", name="ck_bdm_appointments_outcome"),
        sa.CheckConstraint("(status = 'completed') = (outcome IS NOT NULL)", name="ck_bdm_appointments_outcome_completed"),
        sa.CheckConstraint("next_follow_up_on IS NULL OR status = 'completed'", name="ck_bdm_appointments_follow_up"),
        sa.CheckConstraint("duration_minutes BETWEEN 15 AND 720", name="ck_bdm_appointments_duration"),
        sa.CheckConstraint("expected_leads IS NULL OR expected_leads >= 0", name="ck_bdm_appointments_expected_leads"),
        sa.CheckConstraint("expected_revenue IS NULL OR expected_revenue >= 0", name="ck_bdm_appointments_expected_revenue"),
    )
    op.create_index("ix_bdm_appointments_bdm_starts", APPTS, ["bdm_user_id", "starts_at"])
    op.create_index("ix_bdm_appointments_org_starts", APPTS, ["organization_id", "starts_at"])
    op.create_index("ix_bdm_appointments_contact", APPTS, ["contact_id"])
    op.create_table(
        EVENTS,
        _uuid("id", primary_key=True),
        _uuid("appointment_id", sa.ForeignKey(f"{APPTS}.id", ondelete="RESTRICT")),
        _uuid("actor_user_id", sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("old_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(_in("to_status", STATUSES), name="ck_bdm_appointment_events_to_status"),
    )
    op.create_index("ix_bdm_appointment_events_appointment", EVENTS, ["appointment_id", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {APPTS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0068_bdm_appointments: BDM appointments exist. Remove them deliberately first.")
    op.drop_table(EVENTS)
    op.drop_table(APPTS)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
