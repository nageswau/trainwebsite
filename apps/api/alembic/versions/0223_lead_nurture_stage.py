"""itc-004 -- the parked Nurture lead stage in the `enquiries` status CHECK.

Revision ID: 0223_lead_nurture_stage
Revises: 0220_program_syllabus_image

DEC-SCOPE-338 (N2). No existing row changes: the CHECK is widened. The stage list repeats app.lead_stages (test_itc_004_migration).
0001 builds a fresh database from the current models, so the CHECK is replaced with the same text there. The downgrade moves Nurture
leads to Follow-up (where a manual re-activation would put them) so the old CHECK holds; their stage history keeps the Nurture rows.
"""

from alembic import op

revision = "0223_lead_nurture_stage"
down_revision = "0220_program_syllabus_image"
branch_labels = None
depends_on = None

LEADS = "enquiries"
OLD_STAGES = (
    "new",
    "assigned",
    "first_call_pending",
    "contacted",
    "qualified",
    "interested",
    "follow_up",
    "counselling_scheduled",
    "counselling_completed",
    "application_enrollment",
    "converted",
    "not_interested",
    "not_eligible",
    "wrong_number",
    "no_response",
    "lost",
    "duplicate",
)
STAGES = (*OLD_STAGES[:11], "nurture", *OLD_STAGES[11:])  # app.lead_stages: open, parked, closed


def _status_check(stages: tuple[str, ...]) -> str:
    return f"status IN ({', '.join(repr(s) for s in stages)})"


STATUS_CHECK = _status_check(STAGES)


def upgrade() -> None:
    op.drop_constraint("ck_enquiries_status", LEADS, type_="check")
    op.create_check_constraint("ck_enquiries_status", LEADS, STATUS_CHECK)


def downgrade() -> None:
    op.execute(f"UPDATE {LEADS} SET status = 'follow_up', stage_changed_at = now() WHERE status = 'nurture'")
    op.drop_constraint("ck_enquiries_status", LEADS, type_="check")
    op.create_check_constraint("ck_enquiries_status", LEADS, _status_check(OLD_STAGES))
