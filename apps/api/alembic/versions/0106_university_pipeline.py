"""upc-007 -- partnership stage engine: stored stage, Lost flag, stage history.

Revision ID: 0106_university_pipeline
Revises: 0105_university_master

docs/superpowers/specs/2026-10-08-upc-007-partnership-pipeline-design.md §2 (DEC-SCOPE-121). Every existing university starts at
`target_university` with `stage_changed_at = created_at` (PS2: no partner status is invented); no history rows are written. 0001 builds a
fresh database from the current models, which already carry all of this, so each step is guarded. CHECKS / HISTORY_CHECKS repeat
app.models.UNIVERSITY_PIPELINE_CHECKS / UNIVERSITY_STAGE_HISTORY_CHECKS (test_upc_007_migration). downgrade() refuses while stage history,
a lost university or one past `target_university` exists: dropping the columns would lose that pipeline state.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0106_university_pipeline"
down_revision = "0105_university_master"
branch_labels = None
depends_on = None

TABLE = "universities"
HISTORY = "university_stage_history"
FIRST = "target_university"
STAGES = (
    "target_university", "researching", "contact_identified", "initial_contact", "interested", "meeting_scheduled", "meeting_completed",
    "proposal_sent", "commercial_discussion", "documents_shared", "agreement_under_review", "agreement_signed", "partner_activated",
    "student_recruitment_started", "active_partner",
)  # fmt: skip
CHECKS = {
    "ck_universities_stage": f"stage IN ({', '.join(repr(s) for s in STAGES)})",
    "ck_universities_lost": "(lost_at IS NULL) = (lost_reason IS NULL)",
}
HISTORY_CHECKS = {
    "ck_university_stage_history_kind": "kind IN ('move', 'lost', 'reopened')",
    "ck_university_stage_history_note": "kind = 'move' OR note IS NOT NULL",
}
INDEX = "ix_universities_stage"
UUID = postgresql.UUID(as_uuid=True)


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspector()
    present = set() if inspector is None else {c["name"] for c in inspector.get_columns(TABLE)}
    if "stage" not in present:
        op.add_column(TABLE, sa.Column("stage", sa.String(40), nullable=False, server_default=FIRST))
    if "stage_changed_at" not in present:
        op.add_column(TABLE, sa.Column("stage_changed_at", sa.DateTime(timezone=True), nullable=True))
        op.execute(sa.text(f"UPDATE {TABLE} SET stage_changed_at = created_at"))
        op.alter_column(TABLE, "stage_changed_at", nullable=False, server_default=sa.func.now())
    if "lost_at" not in present:
        op.add_column(TABLE, sa.Column("lost_at", sa.DateTime(timezone=True), nullable=True))
    if "lost_reason" not in present:
        op.add_column(TABLE, sa.Column("lost_reason", sa.String(500), nullable=True))

    names = set() if inspector is None else ({c["name"] for c in inspector.get_check_constraints(TABLE)} | {i["name"] for i in inspector.get_indexes(TABLE)})
    for name, sql in CHECKS.items():
        if name not in names:
            op.create_check_constraint(name, TABLE, sql)
    if INDEX not in names:
        op.create_index(INDEX, TABLE, ["stage"])

    if inspector is None or HISTORY not in inspector.get_table_names():
        op.create_table(
            HISTORY,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("university_id", UUID, sa.ForeignKey("universities.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("from_stage", sa.String(40), nullable=False),
            sa.Column("to_stage", sa.String(40), nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in HISTORY_CHECKS.items()),
        )
        op.create_index("ix_university_stage_history_university", HISTORY, ["university_id", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql:
        found = op.get_bind().execute(sa.text(f"SELECT 1 FROM {HISTORY} UNION ALL SELECT 1 FROM {TABLE} WHERE lost_at IS NOT NULL OR stage <> '{FIRST}' LIMIT 1")).first()
        if found:
            raise RuntimeError("Cannot downgrade 0106_university_pipeline: stage history, lost or moved universities exist. Remove them deliberately first.")
    op.drop_table(HISTORY)
    op.drop_index(INDEX, table_name=TABLE)
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    for column in ("lost_reason", "lost_at", "stage_changed_at", "stage"):
        op.drop_column(TABLE, column)
