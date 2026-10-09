"""rec-020 -- interview management: interviews gains code / round / status / interviewer / location / contact / creator; interview_events;
interview_code_seq.

Revision ID: 0133_interview_management
Revises: 0132_university_courses

docs/superpowers/specs/2026-10-09-rec-020-interview-management-design.md §2 (DEC-SCOPE-148). 0001 builds a fresh database from the current
models, which already carry these columns and the table, so every step is guarded. The backfill numbers existing interviews in creation
order and maps the legacy free-text `result` onto a status (selected / rejected / on_hold kept; any other value -> on_hold; none ->
scheduled). No events are backfilled. CHECKS repeats app.models.INTERVIEW_CHECKS (test_rec_020_migration). downgrade() refuses while any
interview history exists: entered data is never dropped silently.

Re-chained twice on 2026-10-09:
- Drafted as `0124_interview_management` (DEC-SCOPE-139, API §12BG, RBAC §2.65) on `0122_candidate_skills`.
- rec-010 (`0123`), upc-026 (`0124`) and upc-012 (`0125`) merged first, so it became `0126` (DEC-SCOPE-141, §12BI, §2.67).
- upc-020, upc-014, upc-008, upc-016, upc-009, upc-021 and upc-017 then merged first (`0126_partnership_tasks` .. `0132_university_courses`,
  DEC-SCOPE-141..147), so this is `0133` (DEC-SCOPE-148, API §12BP, RBAC §2.74).

A database stamped at a draft is re-stamped with `alembic stamp --purge 0122_candidate_skills`, then `upgrade head` (every step is
guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0133_interview_management"
down_revision = "0132_university_courses"
branch_labels = None
depends_on = None

TABLE, EVENTS, SEQ = "interviews", "interview_events", "interview_code_seq"
UNIQUE = "interviews_interview_code_key"
UUID = postgresql.UUID(as_uuid=True)
ROUNDS = ("hr_round", "technical_round", "manager_round", "final_round", "client_round")
STATUSES = ("scheduled", "confirmed", "completed", "rescheduled", "no_show", "selected", "rejected", "on_hold")
CODE_DEFAULT = "'INT-' || to_char(nextval('interview_code_seq'), 'FM999999999000000')"


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


CHECKS = {  # must equal app.models.INTERVIEW_CHECKS (test_rec_020_migration)
    "ck_interviews_status": f"status IN ({_in(STATUSES)})",
    "ck_interviews_round": f"round IS NULL OR round IN ({_in(ROUNDS)})",
}
EVENT_CHECKS = {"ck_interview_events_event": "event IN ('scheduled', 'rescheduled', 'status')"}
INDEXES = {"ix_interviews_status_scheduled": (TABLE, ["status", "scheduled_at"]), "ix_interview_events_interview": (EVENTS, ["interview_id", "position"])}

BACKFILL = f"""
UPDATE {TABLE} i SET
  interview_code = 'INT-' || to_char(n.rn, 'FM999999999000000'),
  status = CASE WHEN i.result IN ('selected', 'rejected', 'on_hold') THEN i.result WHEN coalesce(btrim(i.result), '') <> '' THEN 'on_hold' ELSE 'scheduled' END
FROM (SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM {TABLE}) n
WHERE n.id = i.id AND i.interview_code IS NULL
"""
SET_SEQUENCE = f"SELECT setval('{SEQ}', greatest(count(*), 1), count(*) > 0) FROM {TABLE}"


def _inspect():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspect()
    tables = set(inspector.get_table_names()) if inspector else set()
    columns = {c["name"] for c in inspector.get_columns(TABLE)} if inspector else set()
    checks = {c["name"] for c in inspector.get_check_constraints(TABLE)} if inspector else set()
    indexes = {i["name"] for i in inspector.get_indexes(TABLE)} if inspector else set()
    uniques = {u["name"] for u in inspector.get_unique_constraints(TABLE)} if inspector else set()

    def fk(target: str):
        return sa.ForeignKey(target, ondelete="RESTRICT")

    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}")
    added = "interview_code" not in columns
    for column in (
        sa.Column("interview_code", sa.String(20), nullable=True),
        sa.Column("round", sa.String(20), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'scheduled'")),
        sa.Column("interviewer", sa.String(160), nullable=True),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("contact_id", UUID, fk("company_contacts.id"), nullable=True),
        sa.Column("created_by_user_id", UUID, fk("users.id"), nullable=True),
    ):
        if column.name not in columns:
            op.add_column(TABLE, column)
    if added:
        op.execute(BACKFILL)
        op.execute(SET_SEQUENCE)
        op.alter_column(TABLE, "interview_code", nullable=False, server_default=sa.text(CODE_DEFAULT))
    if UNIQUE not in uniques:
        op.create_unique_constraint(UNIQUE, TABLE, ["interview_code"])
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)
    if EVENTS not in tables:
        when = sa.DateTime(timezone=True)
        op.create_table(
            EVENTS,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("interview_id", UUID, fk(f"{TABLE}.id"), nullable=False),
            sa.Column("event", sa.String(16), nullable=False),
            sa.Column("from_status", sa.String(16), nullable=True),
            sa.Column("to_status", sa.String(16), nullable=True),
            sa.Column("old_scheduled_at", when, nullable=True),
            sa.Column("new_scheduled_at", when, nullable=True),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("actor_user_id", UUID, fk("users.id"), nullable=True),
            sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
            sa.Column("created_at", when, server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in EVENT_CHECKS.items()),
        )
        op.create_index("ix_interview_events_interview", EVENTS, ["interview_id", "position"])
    if "ix_interviews_status_scheduled" not in indexes:
        op.create_index("ix_interviews_status_scheduled", TABLE, ["status", "scheduled_at"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {EVENTS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0133_interview_management: interview history exists. Clear it deliberately first.")
    op.drop_table(EVENTS)
    op.drop_index("ix_interviews_status_scheduled", table_name=TABLE)
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    for name in ("created_by_user_id", "contact_id", "location", "interviewer", "status", "round", "interview_code"):
        op.drop_column(TABLE, name)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
