"""rec-007 -- the Job Requirement: §6 columns on `jobs`, the REQ- code (with backfill), the §6 statuses (legacy values mapped, with
history), job_skills (the skills JSON moved into rows) and job_status_history.

Revision ID: 0113_job_requirements
Revises: 0112_company_pipeline

docs/superpowers/specs/2026-10-08-rec-007-job-requirement-design.md §1, §3 (DEC-SCOPE-128). Drafted as 0108 after 0107_candidates; upc-006 (PR #157) took 0108 and DEC-SCOPE-128 first, and rec-004 claims DEC-SCOPE-124. Every new `jobs` column is nullable except
`requirement_code`, which existing rows get in `created_at`, `id` order; new rows get it from the server default, so the employer and
/workflows/it/jobs insert paths are unchanged. J1: draft -> new, open -> requirement_received, closed stays, anything else -> on_hold;
each remapped row gets a job_status_history row (changed_by NULL) whose note keeps the original value. J7: each skills JSON value is
resolved by name, then alias (active skills, case and spacing ignored); an unmatched value is kept as free text (skill_id NULL); the
JSON is then rewritten as the mirror of the rows. 0001 builds a fresh database from the current models, so every object is created only
when missing (0069's idiom). downgrade() refuses while requirement data exists (a §6 value, or a status change by a user); otherwise it
restores the legacy statuses (from the history notes) and drops what it added -- the JSON mirror still holds the skill names.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0113_job_requirements"
down_revision = "0112_company_pipeline"
branch_labels = None
depends_on = None

TABLE, SKILLS, HISTORY = "jobs", "job_skills", "job_status_history"
SEQ = "requirement_code_seq"
CODE_DEFAULT = f"'REQ-' || lpad(nextval('{SEQ}')::text, 6, '0')"
UUID = postgresql.UUID(as_uuid=True)
STATUSES = ("new", "requirement_received", "sourcing", "shortlisting", "profiles_shared", "interviewing", "selected", "joined", "on_hold", "closed", "cancelled")
OPEN = ("requirement_received", "sourcing", "shortlisting", "profiles_shared", "interviewing")
COLUMNS = (
    ("department", sa.String(120), None),
    ("job_category_id", UUID, "rec_job_categories"),
    ("vacancies", sa.Integer(), None),
    ("qualification", sa.String(300), None),
    ("experience_min_months", sa.Integer(), None),
    ("experience_max_months", sa.Integer(), None),
    ("salary_min", sa.Numeric(12, 2), None),
    ("salary_max", sa.Numeric(12, 2), None),
    ("work_mode", sa.String(20), None),
    ("shift", sa.String(20), None),
    ("employment_type", sa.String(20), None),
    ("joining_requirement", sa.String(300), None),
    ("requirement_date", sa.Date(), None),
    ("priority", sa.String(10), None),
    ("assigned_recruiter_user_id", UUID, "users"),
    ("created_by_user_id", UUID, "users"),
)


def _in(column: str, values) -> str:
    return f"{column} IS NULL OR {column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _list(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


CHECKS = {  # must equal app.models.JOB_CHECKS (test_rec_007_migration)
    "ck_jobs_status": f"status IN ({_list(STATUSES)})",
    "ck_jobs_work_mode": _in("work_mode", ("onsite", "remote", "hybrid")),
    "ck_jobs_shift": _in("shift", ("day", "night", "rotational", "flexible")),
    "ck_jobs_employment_type": _in("employment_type", ("full_time", "part_time", "contract", "internship", "temporary")),
    "ck_jobs_priority": _in("priority", ("high", "medium", "low")),
    "ck_jobs_vacancies": "vacancies IS NULL OR vacancies BETWEEN 1 AND 10000",
    "ck_jobs_experience": "(experience_min_months IS NULL OR experience_min_months BETWEEN 0 AND 600) AND (experience_max_months IS NULL OR experience_max_months BETWEEN 0 AND 600)"
    " AND (experience_min_months IS NULL OR experience_max_months IS NULL OR experience_min_months <= experience_max_months)",
    "ck_jobs_salary": "(salary_min IS NULL OR salary_min >= 0) AND (salary_max IS NULL OR salary_max >= 0) AND (salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max)",
}
INDEXES = {"ix_jobs_status": ["status"], "ix_jobs_assigned_recruiter": ["assigned_recruiter_user_id"], "ix_jobs_closes_on": ["closes_on"]}

BACKFILL = f"UPDATE {TABLE} j SET requirement_code = 'REQ-' || lpad(o.n::text, 6, '0') FROM (SELECT id, row_number() OVER (ORDER BY created_at, id) AS n FROM {TABLE}) o WHERE j.id = o.id"
ADVANCE = f"SELECT setval('{SEQ}', (SELECT count(*) FROM {TABLE})) WHERE EXISTS (SELECT 1 FROM {TABLE})"
LEGACY = f"status NOT IN ({_list(STATUSES)})"
MAPPED = "CASE status WHEN 'draft' THEN 'new' WHEN 'open' THEN 'requirement_received' ELSE 'on_hold' END"
MAP_HISTORY = (
    f"INSERT INTO {HISTORY} (id, job_id, from_status, to_status, note, created_at) "
    f"SELECT gen_random_uuid(), id, NULL, {MAPPED}, left('Legacy status ''' || status || '''', 500), now() FROM {TABLE} WHERE {LEGACY}"
)
MAP_STATUS = f"UPDATE {TABLE} SET status = {MAPPED} WHERE {LEGACY}"
# J7: one row per distinct (resolved) name, in the JSON's order; jobs that already have rows are skipped (re-runnable).
MOVE_SKILLS = f"""
WITH raw AS (
    SELECT j.id AS job_id, e.value AS raw, e.ord
    FROM {TABLE} j, json_array_elements_text(CASE WHEN json_typeof(j.skills) = 'array' THEN j.skills ELSE '[]'::json END) WITH ORDINALITY AS e(value, ord)
    WHERE NOT EXISTS (SELECT 1 FROM {SKILLS} s WHERE s.job_id = j.id)
), terms AS (
    SELECT job_id, ord, left(regexp_replace(btrim(raw), '\\s+', ' ', 'g'), 120) AS term FROM raw
), resolved AS (
    SELECT t.job_id, t.ord, t.term, COALESCE(
        (SELECT k.id FROM skills k WHERE k.active AND lower(k.name) = lower(t.term) LIMIT 1),
        (SELECT k.id FROM skills k JOIN skill_aliases a ON a.skill_id = k.id WHERE k.active AND lower(a.alias) = lower(t.term) LIMIT 1)
    ) AS skill_id
    FROM terms t WHERE t.term <> ''
), firsts AS (
    SELECT DISTINCT ON (r.job_id, lower(COALESCE(k.name, r.term))) r.job_id, r.ord, r.skill_id, COALESCE(k.name, r.term) AS name
    FROM resolved r LEFT JOIN skills k ON k.id = r.skill_id
    ORDER BY r.job_id, lower(COALESCE(k.name, r.term)), r.ord
)
INSERT INTO {SKILLS} (id, job_id, skill_id, name, kind, weight, position)
SELECT gen_random_uuid(), job_id, skill_id, name, 'required', 2, row_number() OVER (PARTITION BY job_id ORDER BY ord) - 1 FROM firsts
"""
MIRROR = (
    f"UPDATE {TABLE} j SET skills = COALESCE((SELECT json_agg(s.name ORDER BY s.kind DESC, s.position) FROM {SKILLS} s WHERE s.job_id = j.id), '[]'::json) "
    "WHERE json_typeof(j.skills) = 'array' AND json_array_length(j.skills) > 0"
)
# downgrade: a migration history row holds the original value; every other row maps to the nearest legacy word.
RESTORE_LEGACY = (
    f"UPDATE {TABLE} j SET status = substring(h.note from 'Legacy status ''(.*)''') FROM {HISTORY} h "
    "WHERE h.job_id = j.id AND h.changed_by_user_id IS NULL AND h.from_status IS NULL AND h.note LIKE 'Legacy status %'"
)
LEGACY_WORDS = f"UPDATE {TABLE} SET status = CASE WHEN status IN ('new', 'on_hold') THEN 'draft' WHEN status IN ({_list(OPEN)}) THEN 'open' ELSE 'closed' END WHERE status IN ({_list(STATUSES)})"


def _inspect():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspect()
    tables = set(inspector.get_table_names()) if inspector else set()
    columns = {c["name"] for c in inspector.get_columns(TABLE)} if inspector else set()
    checks = {c["name"] for c in inspector.get_check_constraints(TABLE)} if inspector else set()
    indexes = {i["name"] for i in inspector.get_indexes(TABLE)} if inspector else set()
    uniques = {u["name"] for u in inspector.get_unique_constraints(TABLE)} if inspector else set()
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ} MAXVALUE 999999")
    if "requirement_code" not in columns:
        op.add_column(TABLE, sa.Column("requirement_code", sa.String(20), nullable=True))
        op.execute(BACKFILL)
        op.execute(ADVANCE)
        op.alter_column(TABLE, "requirement_code", nullable=False, server_default=sa.text(CODE_DEFAULT))
    if "uq_jobs_requirement_code" not in uniques:
        op.create_unique_constraint("uq_jobs_requirement_code", TABLE, ["requirement_code"])
    for name, type_, target in COLUMNS:
        if name not in columns:
            fk = [sa.ForeignKey(f"{target}.id")] if target else []
            op.add_column(TABLE, sa.Column(name, type_, *fk, nullable=True))
    if HISTORY not in tables:
        op.create_table(
            HISTORY,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("job_id", UUID, sa.ForeignKey("jobs.id"), nullable=False),
            sa.Column("from_status", sa.String(30), nullable=True),
            sa.Column("to_status", sa.String(30), nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("changed_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_job_status_history_job_id", HISTORY, ["job_id"])
    if SKILLS not in tables:
        op.create_table(
            SKILLS,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("job_id", UUID, sa.ForeignKey("jobs.id"), nullable=False),
            sa.Column("skill_id", UUID, sa.ForeignKey("skills.id"), nullable=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("weight", sa.SmallInteger(), nullable=False),
            sa.Column("position", sa.SmallInteger(), nullable=False),
            sa.CheckConstraint("kind IN ('required', 'preferred')", name="ck_job_skills_kind"),
            sa.CheckConstraint("weight BETWEEN 1 AND 10", name="ck_job_skills_weight"),
        )
        op.create_index("ix_job_skills_job_id", SKILLS, ["job_id"])
        op.create_index("ix_job_skills_skill", SKILLS, ["skill_id"])
        op.create_index("uq_job_skills_name", SKILLS, ["job_id", sa.text("lower(name)")], unique=True)
    op.execute(MAP_HISTORY)
    op.execute(MAP_STATUS)
    op.execute(MOVE_SKILLS)
    op.execute(MIRROR)
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, TABLE, sql)
    for name, cols in INDEXES.items():
        if name not in indexes:
            op.create_index(name, TABLE, cols)


def downgrade() -> None:
    if not op.get_context().as_sql:
        filled = " OR ".join(f"{name} IS NOT NULL" for name, _, _ in COLUMNS)
        bind = op.get_bind()
        by_user = bind.execute(sa.text(f"SELECT 1 FROM {HISTORY} WHERE changed_by_user_id IS NOT NULL LIMIT 1")).first()
        if by_user or bind.execute(sa.text(f"SELECT 1 FROM {TABLE} WHERE {filled} LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0113_job_requirements: job requirement data exists. Clear it deliberately first.")
    for name in INDEXES:
        op.drop_index(name, table_name=TABLE)
    for name in CHECKS:
        op.drop_constraint(name, TABLE, type_="check")
    op.execute(RESTORE_LEGACY)
    op.execute(LEGACY_WORDS)
    op.drop_table(SKILLS)
    op.drop_table(HISTORY)
    for name, _, _ in reversed(COLUMNS):
        op.drop_column(TABLE, name)
    op.drop_constraint("uq_jobs_requirement_code", TABLE, type_="unique")
    op.drop_column(TABLE, "requirement_code")
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
