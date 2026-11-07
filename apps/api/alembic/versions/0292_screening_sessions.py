"""pob-020 -- question bank, versioned forms, screening sessions and answers (DEC-SCOPE-414 S1-S4).

Revision ID: 0292_screening_sessions
Revises: 0291_recruitment_notices

docs/superpowers/specs/2026-11-06-pob-020-screening-forms-design.md. Additive: five new tables. `application_screenings` is not changed; each of
its rows is copied to one `legacy` session (Q-15, S3). Every step is guarded (0001's `create_all` already builds today's models on a fresh
database) and the seed and copy are idempotent. The CHECKs and catalogues are frozen copies of the models' values. The downgrade drops the
five tables; the original checklist rows were never touched, so no rec-018 data is lost.
"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0292_screening_sessions"
down_revision = "0291_recruitment_notices"
branch_labels = None
depends_on = None

CATEGORIES = ("experience", "technical", "communication", "availability", "compensation")
FORMATS = ("text", "yes_no", "numeric", "choice", "rating")
RECOMMENDATIONS = ("pass", "hold", "reject")
KINDS = ("form", "legacy")
KNOCKOUT_STATUSES = ("none", "pending", "approved")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


QUESTION_CHECKS = {"category": _in("category", CATEGORIES), "format": _in("format", FORMATS)}
BANK_CHECKS = {f"ck_screening_questions_{k}": v for k, v in QUESTION_CHECKS.items()}
FORM_QUESTION_CHECKS = {**{f"ck_screening_form_questions_{k}": v for k, v in QUESTION_CHECKS.items()}, "ck_screening_form_questions_knockout": "NOT is_knockout OR format = 'yes_no'"}
FORM_CHECKS = {"ck_screening_forms_knockout": _in("knockout_status", KNOCKOUT_STATUSES)}
SESSION_CHECKS = {
    "ck_screening_sessions_kind": _in("kind", KINDS),
    "ck_screening_sessions_recommendation": _in("recommendation", RECOMMENDATIONS),
    "ck_screening_sessions_form": "(kind = 'form') = (form_id IS NOT NULL AND form_version IS NOT NULL)",
    "ck_screening_sessions_override": "NOT knockout_overridden OR override_reason IS NOT NULL",
}
ANSWER_CHECKS = {"ck_screening_answers_score": "score IS NULL OR score BETWEEN 0 AND 5"}

# S1 (NEEDS_CONFIRMATION): the source's §10 wording is not on file. One editable question per category, in this order.
DEFAULT_NAME = "Standard 5-category screening"
DEFAULT_QUESTIONS = (
    ("experience", "How many years of relevant experience do you have, and what is your highest qualification?", "text", "Relevant to the requirement's experience and qualification"),
    ("technical", "Walk me through a recent project using the skills this role needs.", "text", "Depth and hands-on use of the required skills"),
    ("communication", "How well does the candidate communicate? (Screener's rating)", "rating", "Clear, structured and professional"),
    ("availability", "What is your notice period, and are you able to work from the requirement's location?", "text", "Fits the requirement's joining date and location"),
    ("compensation", "What are your current and expected salaries?", "text", "Within the requirement's budget"),
)
# S3: frozen copy of application_screening.LEGACY_RECOMMENDATION; the snapshot is application_screening.FIELDS.
LEGACY_COPY = """
INSERT INTO screening_sessions (id, application_id, kind, screened_by_user_id, notes, recommendation, knockout_triggered, knockout_overridden, legacy_snapshot, created_at, updated_at)
SELECT gen_random_uuid(), s.application_id, 'legacy', s.screened_by_user_id, s.remarks,
       CASE s.result WHEN 'shortlisted' THEN 'pass' WHEN 'rejected' THEN 'reject' ELSE 'hold' END, false, false,
       json_build_object(
           'qualification_verified', s.qualification_verified, 'experience_verified', s.experience_verified, 'skills_verified', s.skills_verified,
           'expected_salary', s.expected_salary::double precision, 'notice_days', s.notice_days, 'location_preference', s.location_preference,
           'communication_rating', s.communication_rating, 'technical_rating', s.technical_rating, 'availability', s.availability,
           'willing_to_relocate', s.willing_to_relocate, 'remarks', s.remarks, 'result', s.result
       ),
       s.updated_at, s.updated_at
FROM application_screenings s
WHERE NOT EXISTS (SELECT 1 FROM screening_sessions x WHERE x.application_id = s.application_id AND x.kind = 'legacy')
"""


def _checks(checks: dict) -> list:
    return [sa.CheckConstraint(sql, name=name) for name, sql in checks.items()]


def _stamps() -> list:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def _user_fk(name: str) -> sa.Column:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _existing() -> set[str]:
    return set() if op.get_context().as_sql else set(sa.inspect(op.get_bind()).get_table_names())


def _create_tables(tables: set[str]) -> None:
    if "screening_questions" not in tables:
        op.create_table(
            "screening_questions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("category", sa.String(20), nullable=False),
            sa.Column("question", sa.String(500), nullable=False),
            sa.Column("format", sa.String(10), nullable=False),
            sa.Column("choices", sa.JSON(), nullable=True),
            sa.Column("evaluation_criteria", sa.String(1000), nullable=True),
            sa.Column("expected_answer", sa.String(500), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            _user_fk("created_by_user_id"),
            *_stamps(),
            *_checks(BANK_CHECKS),
        )
        op.create_index("uq_screening_questions_question", "screening_questions", ["category", sa.text("lower(question)")], unique=True)
    if "screening_forms" not in tables:
        op.create_table(
            "screening_forms",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True, unique=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("knockout_status", sa.String(10), nullable=False, server_default=sa.text("'none'")),
            _user_fk("knockout_approved_by_user_id"),
            sa.Column("knockout_approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            _user_fk("created_by_user_id"),
            *_stamps(),
            *_checks(FORM_CHECKS),
        )
        op.create_index("uq_screening_forms_template_name", "screening_forms", [sa.text("lower(name)")], unique=True, postgresql_where=sa.text("job_id IS NULL"))
    if "screening_form_questions" not in tables:
        op.create_table(
            "screening_form_questions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("form_id", sa.Uuid(), sa.ForeignKey("screening_forms.id", ondelete="CASCADE"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("position", sa.SmallInteger(), nullable=False),
            sa.Column("question_id", sa.Uuid(), sa.ForeignKey("screening_questions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("category", sa.String(20), nullable=False),
            sa.Column("question", sa.String(500), nullable=False),
            sa.Column("format", sa.String(10), nullable=False),
            sa.Column("choices", sa.JSON(), nullable=True),
            sa.Column("evaluation_criteria", sa.String(1000), nullable=True),
            sa.Column("expected_answer", sa.String(500), nullable=True),
            sa.Column("is_knockout", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("form_id", "version", "position", name="uq_screening_form_questions_position"),
            *_checks(FORM_QUESTION_CHECKS),
        )
    if "screening_sessions" not in tables:
        op.create_table(
            "screening_sessions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("application_id", sa.Uuid(), sa.ForeignKey("job_applications.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("form_id", sa.Uuid(), sa.ForeignKey("screening_forms.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("form_version", sa.Integer(), nullable=True),
            sa.Column("screened_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("notes", sa.String(2000), nullable=True),
            sa.Column("recommendation", sa.String(10), nullable=False),
            sa.Column("knockout_triggered", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("knockout_overridden", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("override_reason", sa.String(500), nullable=True),
            sa.Column("legacy_snapshot", sa.JSON(), nullable=True),
            *_stamps(),
            *_checks(SESSION_CHECKS),
        )
        op.create_index("ix_screening_sessions_application", "screening_sessions", ["application_id", "created_at"])
        op.create_index("ix_screening_sessions_form", "screening_sessions", ["form_id", "form_version"])
    if "screening_answers" not in tables:
        op.create_table(
            "screening_answers",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("session_id", sa.Uuid(), sa.ForeignKey("screening_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("form_question_id", sa.Uuid(), sa.ForeignKey("screening_form_questions.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("answer", sa.String(2000), nullable=False),
            sa.Column("score", sa.SmallInteger(), nullable=True),
            sa.UniqueConstraint("session_id", "form_question_id", name="uq_screening_answers_question"),
            *_checks(ANSWER_CHECKS),
        )


def _seed_default_template() -> None:
    """S1: the bank's five questions and the template that copies them; skipped when a default template already exists."""
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM screening_forms WHERE is_default AND job_id IS NULL")).first():
        return
    form_id = uuid.uuid4()
    bind.execute(sa.text("INSERT INTO screening_forms (id, name, is_default) VALUES (:id, :name, true)"), {"id": form_id, "name": DEFAULT_NAME})
    for position, (category, question, fmt, criteria) in enumerate(DEFAULT_QUESTIONS, start=1):
        values = {"id": uuid.uuid4(), "category": category, "question": question, "format": fmt, "criteria": criteria}
        bind.execute(
            sa.text("INSERT INTO screening_questions (id, category, question, format, evaluation_criteria) VALUES (:id, :category, :question, :format, :criteria) ON CONFLICT DO NOTHING"),
            values,
        )
        bind.execute(
            sa.text(
                "INSERT INTO screening_form_questions (id, form_id, version, position, question_id, category, question, format, evaluation_criteria) "
                "VALUES (:fq, :form, 1, :position, (SELECT id FROM screening_questions WHERE category = :category AND lower(question) = lower(:question)), :category, :question, :format, :criteria)"
            ),
            {**values, "fq": uuid.uuid4(), "form": form_id, "position": position},
        )


def upgrade() -> None:
    _create_tables(_existing())
    if op.get_context().as_sql:
        return
    _seed_default_template()
    op.execute(LEGACY_COPY)


def downgrade() -> None:
    for table in ("screening_answers", "screening_sessions", "screening_form_questions", "screening_forms", "screening_questions"):
        op.drop_table(table)
