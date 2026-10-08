"""rec-017 -- candidate + requirement tracking: `job_applications.candidate_id` (with the R6 candidate backfill), the §12 statuses (legacy
values mapped, with history), `stage_changed_at`, `added_by_user_id`, unique (candidate, job) and job_application_status_history.

Revision ID: 0119_job_application_tracking
Revises: 0118_recruiter_calls

docs/superpowers/specs/2026-10-08-rec-017-candidate-requirement-tracking-design.md §1 (DEC-SCOPE-134).
- Refuses first if a (job, student) pair is duplicated: a merge would re-point interviews and offers, so a person resolves it.
- Every student with an application or a placement profile gets a candidate. A3: one whose email or mobile already belongs to an unlinked
  (external) candidate is linked to it and that candidate stays in the pool (opted_in true); everyone else gets a new candidate from the
  `Edusphere students` source with opted_in false.
- A1 maps the statuses; every existing row gets a history row (changed_by NULL) whose note keeps the legacy value.
- `student_id` becomes nullable (external candidates have no login).
0001 builds a fresh database from the current models, so every object is created only when missing (0114's idiom). downgrade() refuses
while tracking data exists (an application without a student, or a status change by a user); otherwise it restores the legacy statuses
from the history notes. Backfilled candidates are kept: candidates are archived, never deleted (rec-009).
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.notifications.phone import normalise_phone

revision = "0119_job_application_tracking"
down_revision = "0118_recruiter_calls"
branch_labels = None
depends_on = None

TABLE, HISTORY = "job_applications", "job_application_status_history"
UUID = postgresql.UUID(as_uuid=True)
STATUSES = ("sourced", "screened", "shortlisted", "profile_shared", "interview", "selected", "joined", "rejected", "withdrawn")
LEGACY = {  # A1
    "applied": "sourced",
    "screening": "screened",
    "shortlisted": "shortlisted",
    "interview_scheduled": "interview",
    "offer_received": "selected",
    "hired": "joined",
    "rejected": "rejected",
    "withdrawn": "withdrawn",
}
CHECKS = {"ck_job_applications_status": "status IN (" + ", ".join(f"'{s}'" for s in STATUSES) + ")"}  # == app.models.APPLICATION_CHECKS
UNIQUE = "uq_job_applications_candidate_job"
INDEXES = {"ix_job_applications_job_status": ["job_id", "status"], "ix_job_applications_candidate": ["candidate_id"]}
SOURCE_NAME = "Edusphere students"

DUPLICATES = f"SELECT job_id, student_id, count(*) FROM {TABLE} WHERE student_id IS NOT NULL GROUP BY job_id, student_id HAVING count(*) > 1"
STUDENTS = (
    "SELECT u.id, u.full_name, u.email, u.phone FROM users u WHERE u.id IN "
    f"(SELECT student_id FROM {TABLE} WHERE student_id IS NOT NULL UNION SELECT student_id FROM placement_profiles) "
    "AND NOT EXISTS (SELECT 1 FROM candidates c WHERE c.user_id = u.id) ORDER BY u.created_at, u.id"
)
MAPPED = "CASE status " + " ".join(f"WHEN '{old}' THEN '{new}'" for old, new in LEGACY.items()) + " ELSE 'sourced' END"
# Only rows not yet mapped (re-runnable after a downgrade): the legacy words outside the new set, plus words both sets share that have no
# history row yet.
UNMAPPED = f"(status NOT IN ({', '.join(repr(s) for s in STATUSES)}) OR NOT EXISTS (SELECT 1 FROM {HISTORY} h WHERE h.application_id = {TABLE}.id))"
MAP_HISTORY = (
    f"INSERT INTO {HISTORY} (id, application_id, from_status, to_status, note, created_at) "
    f"SELECT gen_random_uuid(), id, NULL, {MAPPED}, left('Legacy status ''' || status || '''', 500), now() FROM {TABLE} WHERE {UNMAPPED}"
)
MAP_STATUS = f"UPDATE {TABLE} SET status = {MAPPED}, stage_changed_at = updated_at WHERE status NOT IN ({', '.join(repr(s) for s in STATUSES)})"
LINK = f"UPDATE {TABLE} a SET candidate_id = c.id FROM candidates c WHERE c.user_id = a.student_id AND a.candidate_id IS NULL"
RESTORE_LEGACY = (
    f"UPDATE {TABLE} a SET status = substring(h.note from 'Legacy status ''(.*)''') FROM {HISTORY} h "
    "WHERE h.application_id = a.id AND h.from_status IS NULL AND h.changed_by_user_id IS NULL AND h.note LIKE 'Legacy status %'"
)
LEGACY_WORDS = f"UPDATE {TABLE} SET status = CASE status " + " ".join(f"WHEN '{new}' THEN '{old}'" for old, new in LEGACY.items()) + " ELSE 'applied' END WHERE status IN ('sourced', 'screened', 'interview', 'selected', 'joined', 'profile_shared')"


def _inspect():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def _source_id(bind) -> uuid.UUID:
    row = bind.execute(sa.text("SELECT id FROM rec_candidate_sources WHERE lower(name) = lower(:n)"), {"n": SOURCE_NAME}).first()
    if row:
        return row[0]
    source_id = uuid.uuid4()
    bind.execute(sa.text("INSERT INTO rec_candidate_sources (id, name) VALUES (:id, :n)"), {"id": source_id, "n": SOURCE_NAME})
    return source_id


def _backfill_candidates(bind) -> None:
    """Step 3 of the spec: link (A3) or create one candidate per student who has none."""
    students = bind.execute(sa.text(STUDENTS)).all()
    if not students:
        return
    source_id = _source_id(bind)
    for user_id, full_name, email, phone in students:
        mobile_key = normalise_phone(phone)
        match = bind.execute(
            sa.text(
                "SELECT id FROM candidates WHERE user_id IS NULL AND (lower(email) = lower(CAST(:e AS varchar)) OR mobile_normalized = CAST(:m AS varchar)) "
                "ORDER BY (lower(email) = lower(CAST(:e AS varchar))) DESC NULLS LAST, created_at LIMIT 1"
            ),
            {"e": email, "m": mobile_key},
        ).first()
        if match:
            bind.execute(sa.text("UPDATE candidates SET user_id = :u, opted_in = true, updated_at = now() WHERE id = :id"), {"u": user_id, "id": match[0]})
            continue
        if mobile_key and bind.execute(sa.text("SELECT 1 FROM candidates WHERE mobile_normalized = :m"), {"m": mobile_key}).first():
            phone, mobile_key = None, None  # already some other candidate's mobile (Q-07): the email alone identifies this one
        email_taken = bind.execute(sa.text("SELECT 1 FROM candidates WHERE lower(email) = lower(:e)"), {"e": email}).first()
        bind.execute(
            sa.text(
                "INSERT INTO candidates (id, candidate_code, name, email, mobile, mobile_normalized, preferred_locations, source_id, status, user_id, "
                "opted_in, created_by_user_id, created_at, updated_at) VALUES (:id, 'CAN-' || lpad(nextval('candidate_code_seq')::text, 6, '0'), "
                ":n, :e, :p, :m, '[]', :src, 'available', :u, false, :u, now(), now())"
            ),
            {"id": uuid.uuid4(), "n": full_name[:160], "e": None if email_taken else email, "p": phone if mobile_key else None, "m": mobile_key, "src": source_id, "u": user_id},
        )


def upgrade() -> None:
    inspector = _inspect()
    tables = set(inspector.get_table_names()) if inspector else set()
    columns = {c["name"]: c for c in inspector.get_columns(TABLE)} if inspector else {}
    checks = {c["name"] for c in inspector.get_check_constraints(TABLE)} if inspector else set()
    indexes = {i["name"] for i in inspector.get_indexes(TABLE)} if inspector else set()
    uniques = {u["name"] for u in inspector.get_unique_constraints(TABLE)} if inspector else set()
    if inspector:
        duplicates = op.get_bind().execute(sa.text(DUPLICATES)).all()
        if duplicates:
            pairs = "; ".join(f"job {j} / student {s} ({n} rows)" for j, s, n in duplicates[:20])
            raise RuntimeError(f"Cannot upgrade to 0119_job_application_tracking: duplicate job applications exist ({pairs}). Merge them first.")
    if "candidate_id" not in columns:
        op.add_column(TABLE, sa.Column("candidate_id", UUID, sa.ForeignKey("candidates.id"), nullable=True))
    if "stage_changed_at" not in columns:
        op.add_column(TABLE, sa.Column("stage_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    if "added_by_user_id" not in columns:
        op.add_column(TABLE, sa.Column("added_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True))
    if HISTORY not in tables:
        op.create_table(
            HISTORY,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("application_id", UUID, sa.ForeignKey(f"{TABLE}.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("from_status", sa.String(30), nullable=True),
            sa.Column("to_status", sa.String(30), nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("changed_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_job_application_status_history_application", HISTORY, ["application_id", "created_at"])
    if inspector:
        _backfill_candidates(op.get_bind())
    op.execute(LINK)
    op.execute(MAP_HISTORY)
    op.execute(MAP_STATUS)
    op.alter_column(TABLE, "candidate_id", nullable=False)
    op.alter_column(TABLE, "student_id", nullable=True)
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)
    if UNIQUE not in uniques:
        op.create_unique_constraint(UNIQUE, TABLE, ["candidate_id", "job_id"])
    for name, cols in INDEXES.items():
        if name not in indexes:
            op.create_index(name, TABLE, cols)


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        external = bind.execute(sa.text(f"SELECT 1 FROM {TABLE} WHERE student_id IS NULL LIMIT 1")).first()
        by_user = bind.execute(sa.text(f"SELECT 1 FROM {HISTORY} WHERE changed_by_user_id IS NOT NULL LIMIT 1")).first()
        if external or by_user:
            raise RuntimeError("Cannot downgrade 0119_job_application_tracking: application tracking data exists. Clear it deliberately first.")
    for name in INDEXES:
        op.drop_index(name, table_name=TABLE)
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    op.execute(RESTORE_LEGACY)
    op.execute(LEGACY_WORDS)
    op.drop_table(HISTORY)
    op.alter_column(TABLE, "student_id", nullable=False)
    op.drop_column(TABLE, "added_by_user_id")
    op.drop_column(TABLE, "stage_changed_at")
    op.drop_column(TABLE, "candidate_id")
