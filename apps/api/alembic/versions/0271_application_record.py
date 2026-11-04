"""hrc-026 -- application record completion: job_applications gains a human code (JA-000001), source, owner, the last candidate-visible
stage and a rejection reason; the status history keeps the reason.

Revision ID: 0271_application_record
Revises: 0270_candidate_routing

docs/superpowers/specs/2026-11-04-hrc-026-application-record-design.md (DEC-SCOPE-394 A1/A4-A7/A9). 0001 builds a fresh database from the
current models, which already carry these columns, so every step is guarded (0133's idiom). The backfill numbers existing applications in
creation order; source = drive tag -> drive, no adder -> portal, an employer adder -> employer, else recruiter; owner = a recruiter adder,
else the requirement's assigned recruiter; candidate_status = the status when candidate-visible, else the last visible stage in the
history, else sourced. Existing rejected rows keep no reason ("not recorded"). CHECKS repeats app.models.APPLICATION_CHECKS (hrc-026 part,
test_hrc_026_migration). No stored status changes, so the downgrade only drops what this adds.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0271_application_record"
down_revision = "0270_candidate_routing"  # drafted on 0269_match_engine; hrc-024 merged 0270 first
branch_labels = None
depends_on = None

TABLE, HISTORY, SEQ = "job_applications", "job_application_status_history", "job_application_code_seq"
UNIQUE = "job_applications_application_code_key"
OWNER_FK = "fk_job_applications_owner_user_id_users"
UUID = postgresql.UUID(as_uuid=True)
STATUSES = ("sourced", "screened", "shortlisted", "profile_shared", "interview", "selected", "joined", "rejected", "withdrawn")
VISIBLE = tuple(s for s in STATUSES if s != "profile_shared")
SOURCES = ("portal", "recruiter", "employer", "drive")
REASONS = (
    "skills_mismatch", "experience_mismatch", "qualification_mismatch", "salary_mismatch", "location_mismatch", "screening_not_cleared",
    "interview_not_cleared", "not_reachable", "client_rejected", "position_filled", "other",
)
CODE_DEFAULT = "'JA-' || to_char(nextval('job_application_code_seq'), 'FM999999999000000')"


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


CHECKS = {  # must equal the hrc-026 entries of app.models.APPLICATION_CHECKS (test_hrc_026_migration)
    "ck_job_applications_source": f"source IN ({_in(SOURCES)})",
    "ck_job_applications_candidate_status": f"candidate_status IN ({_in(VISIBLE)})",
    "ck_job_applications_rejection_reason": f"rejection_reason IS NULL OR (status = 'rejected' AND rejection_reason IN ({_in(REASONS)}))",
}

BACKFILL = f"""
UPDATE {TABLE} a SET
  application_code = 'JA-' || to_char(n.rn, 'FM999999999000000'),
  source = CASE WHEN a.drive_id IS NOT NULL THEN 'drive' WHEN a.added_by_user_id IS NULL THEN 'portal'
                WHEN adder.role = 'employer' THEN 'employer' ELSE 'recruiter' END,
  owner_user_id = CASE WHEN adder.role = 'placement_team' THEN adder.id ELSE j.assigned_recruiter_user_id END,
  candidate_status = CASE WHEN a.status IN ({_in(VISIBLE)}) THEN a.status ELSE coalesce((
      SELECT h.to_status FROM {HISTORY} h WHERE h.application_id = a.id AND h.to_status IN ({_in(VISIBLE)})
      ORDER BY h.created_at DESC, h.id DESC LIMIT 1), 'sourced') END
FROM (SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM {TABLE}) n, jobs j, {TABLE} self
LEFT JOIN users adder ON adder.id = self.added_by_user_id
WHERE n.id = a.id AND self.id = a.id AND j.id = a.job_id AND a.application_code IS NULL
"""
SET_SEQUENCE = f"SELECT setval('{SEQ}', greatest(count(*), 1), count(*) > 0) FROM {TABLE}"


def _inspect():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspect()
    columns = {c["name"] for c in inspector.get_columns(TABLE)} if inspector else set()
    history_columns = {c["name"] for c in inspector.get_columns(HISTORY)} if inspector else set()
    checks = {c["name"] for c in inspector.get_check_constraints(TABLE)} if inspector else set()
    uniques = {u["name"] for u in inspector.get_unique_constraints(TABLE)} if inspector else set()

    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}")
    added = "application_code" not in columns
    for column in (
        sa.Column("application_code", sa.String(20), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default=sa.text("'recruiter'")),
        sa.Column("owner_user_id", UUID, sa.ForeignKey("users.id", name=OWNER_FK, ondelete="RESTRICT"), nullable=True),
        sa.Column("candidate_status", sa.String(30), nullable=False, server_default=sa.text("'sourced'")),
        sa.Column("rejection_reason", sa.String(40), nullable=True),
    ):
        if column.name not in columns:
            op.add_column(TABLE, column)
    if "rejection_reason" not in history_columns:
        op.add_column(HISTORY, sa.Column("rejection_reason", sa.String(40), nullable=True))
    if added:
        op.execute(BACKFILL)
        op.execute(SET_SEQUENCE)
        op.alter_column(TABLE, "application_code", nullable=False, server_default=sa.text(CODE_DEFAULT))
    if UNIQUE not in uniques:
        op.create_unique_constraint(UNIQUE, TABLE, ["application_code"])
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)


def downgrade() -> None:
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    op.drop_column(HISTORY, "rejection_reason")
    for column in ("rejection_reason", "candidate_status", "owner_user_id", "source", "application_code"):
        op.drop_column(TABLE, column)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
