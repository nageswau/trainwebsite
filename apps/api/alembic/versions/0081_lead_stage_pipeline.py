"""tel-004 -- the lead pipeline: `lead_stage_history`, the legacy status mapping and the `enquiries.status` CHECK.

Revision ID: 0081_lead_stage_pipeline
Revises: 0080_tel_targets

docs/superpowers/specs/2026-10-06-tel-004-lead-pipeline-design.md §3 (DEC-SCOPE-081). PL1: `new`, `contacted`, `qualified`, `lost` (and
any other value already a stage) are kept; `converted` becomes `application_enrollment` when a student is linked, else `follow_up`; any
other text becomes `new`. Each changed lead keeps its original text in `metadata_json.legacy_status` and gets one history row
(`legacy_mapping`, no actor). 0001 builds a fresh database from the current models, which already carry all of this, so the upgrade is
guarded (0074's idiom). downgrade() refuses once any real stage change has been recorded; otherwise it restores each legacy status.

Re-chained twice on 2026-10-06. Drafted as `0079_lead_stage_pipeline` (DEC-SCOPE-078) on 0078; bdm-005 took `0079_bdm_mous` /
DEC-SCOPE-078 (main @ `230a043f`), then bdm-013 took DEC-SCOPE-079 and tel-022 took `0080_tel_targets` / DEC-SCOPE-080 (main @
`a38955d5`), so this revision is `0081_lead_stage_pipeline` after `0080_tel_targets` (one head) and the decision is DEC-SCOPE-081.
A database stamped at `0079_`/`0080_lead_stage_pipeline` is re-stamped with `alembic stamp --purge <the revision before it on main>`
then `upgrade head` (the upgrade is guarded, so the re-run is harmless).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0081_lead_stage_pipeline"
down_revision = "0080_tel_targets"
branch_labels = None
depends_on = None

TABLE = "lead_stage_history"
# Frozen copy of app/lead_stages.STAGES; test_tel_004_migration asserts it stays identical.
STAGES = ("new", "assigned", "first_call_pending", "contacted", "qualified", "interested", "follow_up", "counselling_scheduled",
          "counselling_completed", "application_enrollment", "converted", "not_interested", "not_eligible", "wrong_number", "no_response",
          "lost")
STATUS_CHECK = f"status IN ({', '.join(repr(s) for s in STAGES)})"
KEPT = ", ".join(repr(s) for s in STAGES if s != "converted")
TARGET = (
    f"CASE WHEN status IN ({KEPT}) THEN status "
    "WHEN status = 'converted' AND converted_user_id IS NOT NULL THEN 'application_enrollment' "
    "WHEN status = 'converted' THEN 'follow_up' ELSE 'new' END"
)


def upgrade() -> None:
    if not op.get_context().as_sql and sa.inspect(op.get_bind()).has_table(TABLE):
        return
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid, primary_key=True),
        sa.Column("lead_id", uuid, sa.ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("from_stage", sa.String(40), nullable=False),
        sa.Column("to_stage", sa.String(40), nullable=False),
        sa.Column("event", sa.String(30), nullable=False),
        sa.Column("actor_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lead_stage_history_lead", TABLE, ["lead_id", "position"])

    # PL1: history first (it reads the old status), oldest lead first so `position` follows creation order.
    op.execute(
        f"INSERT INTO {TABLE} (id, lead_id, from_stage, to_stage, event) "
        f"SELECT gen_random_uuid(), id, status, {TARGET}, 'legacy_mapping' FROM enquiries "
        f"WHERE status IS DISTINCT FROM {TARGET} ORDER BY created_at, id"
    )
    op.execute(
        "UPDATE enquiries SET metadata_json = (COALESCE(metadata_json::jsonb, '{}'::jsonb) || jsonb_build_object('legacy_status', status))::json, "
        f"status = {TARGET}, stage_changed_at = now() WHERE status IS DISTINCT FROM {TARGET}"
    )
    op.create_check_constraint("ck_enquiries_status", "enquiries", STATUS_CHECK)


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} WHERE event <> 'legacy_mapping' LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0081_lead_stage_pipeline: lead stage history exists. Clear it deliberately first.")
    op.drop_constraint("ck_enquiries_status", "enquiries", type_="check")
    op.execute(
        "UPDATE enquiries SET status = metadata_json::jsonb ->> 'legacy_status', metadata_json = (metadata_json::jsonb - 'legacy_status')::json "
        "WHERE metadata_json::jsonb ? 'legacy_status'"
    )
    op.drop_index("ix_lead_stage_history_lead", table_name=TABLE)
    op.drop_table(TABLE)
