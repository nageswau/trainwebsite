"""bdm-004 -- organization pipelines: pipeline_stage + Lost on bdm_organizations, and bdm_pipeline_events.

Revision ID: 0073_bdm_pipeline
Revises: 0072_bdm_meeting_reports

docs/superpowers/specs/2026-10-05-bdm-004-organization-pipelines-design.md §5 (DEC-SCOPE-071). Additive: existing rows get
'prospect' from the column default (valid for all three types) and no history row. 0001 builds a fresh database from the current
models, which already carry the columns, CHECKs, index and table, so each is created only when missing. MANUAL_STAGES is a frozen copy
of app.bdm_stages.MANUAL_STAGES and CHECKS must equal app.models.BDM_PIPELINE_CHECKS (test_bdm_004_migration). downgrade() refuses
while any pipeline data exists: recorded moves are never dropped silently.

Re-chained 2026-10-05 on merging `main` @ `c85849d8`: cut as `0072_bdm_pipeline` after `0071_bdm_activities` (DEC-SCOPE-070), but
bdm-007's `0072_bdm_meeting_reports` (DEC-SCOPE-070) reached `main` first, so this revision is now `0073_bdm_pipeline` after it (one
head) and the decision is DEC-SCOPE-071. A database stamped at `0072_bdm_pipeline` is re-stamped with
`alembic stamp --purge 0071_bdm_activities` then `upgrade head` (every create here is guarded, so the re-run is harmless).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0073_bdm_pipeline"
down_revision = "0072_bdm_meeting_reports"
branch_labels = None
depends_on = None

TABLE = "bdm_organizations"
EVENTS = "bdm_pipeline_events"
INDEX = "ix_bdm_organizations_type_stage"
MANUAL_STAGES = {
    "agent": ("prospect", "contacted", "meeting_scheduled", "meeting_completed", "interested", "proposal_agreement", "agreement_signed"),
    "school": ("prospect", "contacted", "meeting", "presentation", "proposal", "negotiation", "mou", "signed"),
    "college": ("prospect", "contacted", "meeting", "presentation", "proposal", "mou_negotiation", "mou_signed", "college_activated"),
}


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {
    "ck_bdm_organizations_pipeline_stage": " OR ".join(
        f"(bdm_type = '{bdm_type}' AND {_in_list('pipeline_stage', stages)})" for bdm_type, stages in MANUAL_STAGES.items()
    ),
    "ck_bdm_organizations_lost": "(lost_at IS NULL) = (lost_reason IS NULL)",
}


def _present() -> tuple[set[str], set[str], set[str], set[str]]:
    if op.get_context().as_sql:  # offline SQL: emit everything
        return set(), set(), set(), set()
    inspector = sa.inspect(op.get_bind())
    return (
        {c["name"] for c in inspector.get_columns(TABLE)},
        {c["name"] for c in inspector.get_check_constraints(TABLE)},
        {i["name"] for i in inspector.get_indexes(TABLE)},
        set(inspector.get_table_names()),
    )


def upgrade() -> None:
    columns, checks, indexes, tables = _present()
    if "pipeline_stage" not in columns:
        op.add_column(TABLE, sa.Column("pipeline_stage", sa.String(40), nullable=False, server_default="prospect"))
    if "lost_at" not in columns:
        op.add_column(TABLE, sa.Column("lost_at", sa.DateTime(timezone=True), nullable=True))
    if "lost_reason" not in columns:
        op.add_column(TABLE, sa.Column("lost_reason", sa.String(500), nullable=True))
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)
    if INDEX not in indexes:
        op.create_index(INDEX, TABLE, ["bdm_type", "pipeline_stage"])
    if EVENTS not in tables:
        uuid = postgresql.UUID(as_uuid=True)
        op.create_table(
            EVENTS,
            sa.Column("id", uuid, primary_key=True),
            sa.Column("organization_id", uuid, sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("actor_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("from_stage", sa.String(40), nullable=False),
            sa.Column("to_stage", sa.String(40), nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("kind IN ('move', 'lost', 'revived')", name="ck_bdm_pipeline_events_kind"),
            sa.CheckConstraint("kind = 'move' OR note IS NOT NULL", name="ck_bdm_pipeline_events_note"),
        )
        op.create_index("ix_bdm_pipeline_events_org", EVENTS, ["organization_id", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        recorded = bind.execute(sa.text(f"SELECT 1 FROM {EVENTS} LIMIT 1")).first()
        moved = bind.execute(sa.text(f"SELECT 1 FROM {TABLE} WHERE pipeline_stage <> 'prospect' OR lost_at IS NOT NULL LIMIT 1")).first()
        if recorded or moved:
            raise RuntimeError("Cannot downgrade 0072_bdm_pipeline: pipeline data exists. Clear it deliberately first.")
    op.drop_table(EVENTS)
    op.drop_index(INDEX, TABLE)
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    for name in ("lost_reason", "lost_at", "pipeline_stage"):
        op.drop_column(TABLE, name)
