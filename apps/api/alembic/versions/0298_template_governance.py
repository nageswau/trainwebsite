"""pob-023 -- template library governance (DEC-SCOPE-408 G1-G7).

Revision ID: 0298_template_governance
Revises: 0297_crm_import_merge

docs/superpowers/specs/2026-11-05-pob-023-template-governance-design.md. On `recruiter_message_templates`:
- LinkedIn and calling-script channels (no kind), the §14 category, metadata, and `status`. `status` replaces `active`: true becomes
  approved, false becomes archived, so no data is lost.
- Personal ownership, calling steps, `version`, the authors and `last_used_at`.
- The shared-name index becomes partial, and a per-author one is added.
- New `recruiter_template_versions` table, with v1 written for every existing row.

Every step is guarded, because 0001's `create_all` already builds today's models on a fresh database. The checks are frozen copies of
`models.RECRUITER_TEMPLATE_CHECKS`. The downgrade restores `active` from `status`, and refuses if a LinkedIn or call template or a
personal one exists, because 0120's schema cannot hold them.
"""

import sqlalchemy as sa

from alembic import op

revision = "0298_template_governance"
down_revision = "0297_crm_import_merge"
branch_labels = None
depends_on = None

T = "recruiter_message_templates"
WHATSAPP_KINDS = ("candidate_profiles", "jd_confirmation", "interview_reminder", "follow_up", "requirement_update")
EMAIL_KINDS = (
    "company_introduction", "recruitment_proposal", "candidate_profiles", "jd_acknowledgement", "interview_confirmation", "offer_follow_up",
    "joining_confirmation",
)  # fmt: skip
CANDIDATE_EMAIL_KINDS = ("interview_confirmation", "offer_follow_up", "joining_confirmation")  # G2: the rest of email is "company"
TEMPLATE_CHECKS = {
    "ck_recruiter_message_templates_channel": "channel IN ('whatsapp', 'email', 'linkedin', 'call')",
    "ck_recruiter_message_templates_kind": (
        f"(channel = 'whatsapp' AND kind IN ({', '.join(repr(k) for k in WHATSAPP_KINDS)})) OR "
        f"(channel = 'email' AND kind IN ({', '.join(repr(k) for k in EMAIL_KINDS)})) OR "
        "(channel IN ('linkedin', 'call') AND kind IS NULL)"
    ),
    "ck_recruiter_message_templates_subject": "(channel = 'email') = (subject IS NOT NULL)",
    "ck_recruiter_message_templates_category": "category IN ('company', 'linkedin', 'whatsapp', 'calling', 'college_tpo', 'candidate')",
    "ck_recruiter_message_templates_status": "status IN ('draft', 'approved', 'archived')",
    "ck_recruiter_message_templates_steps": "(channel = 'call') = (steps IS NOT NULL)",
    "ck_recruiter_message_templates_personal": "owner_user_id IS NULL OR status <> 'approved'",
}
OLD_CHECKS = {
    "ck_recruiter_message_templates_channel": "channel IN ('whatsapp', 'email')",
    "ck_recruiter_message_templates_kind": (
        f"(channel = 'whatsapp' AND kind IN ({', '.join(repr(k) for k in WHATSAPP_KINDS)})) OR "
        f"(channel = 'email' AND kind IN ({', '.join(repr(k) for k in EMAIL_KINDS)}))"
    ),
}
NAME_INDEX, OWNER_INDEX = "uq_recruiter_message_templates_channel_name", "uq_recruiter_message_templates_owner_name"
COLUMNS = (
    ("category", lambda: sa.Column("category", sa.String(20), nullable=False, server_default=sa.text("'company'"))),
    ("purpose", lambda: sa.Column("purpose", sa.String(200), nullable=True)),
    ("language", lambda: sa.Column("language", sa.String(40), nullable=False, server_default=sa.text("'English'"))),
    ("department", lambda: sa.Column("department", sa.String(80), nullable=True)),
    ("industry", lambda: sa.Column("industry", sa.String(80), nullable=True)),
    ("role_type", lambda: sa.Column("role_type", sa.String(80), nullable=True)),
    ("status", lambda: sa.Column("status", sa.String(10), nullable=False, server_default=sa.text("'approved'"))),
    ("owner_user_id", lambda: sa.Column("owner_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)),
    ("steps", lambda: sa.Column("steps", sa.JSON(), nullable=True)),
    ("version", lambda: sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"))),
    ("created_by_user_id", lambda: sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)),
    ("updated_by_user_id", lambda: sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)),
    ("last_used_at", lambda: sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True)),
)
BACKFILL_CATEGORY = f"""
UPDATE {T} t SET category = CASE
    WHEN channel = 'whatsapp' THEN 'whatsapp'
    WHEN kind IN ({', '.join(repr(k) for k in CANDIDATE_EMAIL_KINDS)}) THEN 'candidate'
    ELSE 'company' END
WHERE NOT EXISTS (SELECT 1 FROM recruiter_template_versions v WHERE v.template_id = t.id)
"""  # rows from before 0286 (no version yet), including 0120's seed on a fresh database
# G7: v1 of every row that has no version yet -- the content keys of services/recruiter_messages.VERSIONED
BACKFILL_VERSIONS = f"""
INSERT INTO recruiter_template_versions (id, template_id, version, content, edited_by_user_id, created_at)
SELECT gen_random_uuid(), t.id, t.version, json_build_object(
    'name', t.name, 'kind', t.kind, 'category', t.category, 'subject', t.subject, 'body', t.body, 'steps', t.steps, 'purpose', t.purpose,
    'language', t.language, 'department', t.department, 'industry', t.industry, 'role_type', t.role_type), NULL, t.created_at
FROM {T} t WHERE NOT EXISTS (SELECT 1 FROM recruiter_template_versions v WHERE v.template_id = t.id)
"""


def _state() -> tuple[set, set, set, set]:
    if op.get_context().as_sql:
        return set(), set(), set(), set()
    inspector = sa.inspect(op.get_bind())
    return (
        set(inspector.get_table_names()),
        {c["name"] for c in inspector.get_columns(T)},
        {i["name"] for i in inspector.get_indexes(T)},
        {c["name"]: c["sqltext"] for c in inspector.get_check_constraints(T)},
    )


def _replace_check(name: str, sql: str, existing: dict) -> None:
    if name in existing:
        op.drop_constraint(name, T, type_="check")
    op.create_check_constraint(name, T, sql)


def upgrade() -> None:
    tables, columns, indexes, checks = _state()
    for name, column in COLUMNS:
        if name not in columns:
            op.add_column(T, column())
    if "active" in columns:
        op.execute(f"UPDATE {T} SET status = CASE WHEN active THEN 'approved' ELSE 'archived' END")
        op.drop_column(T, "active")
    op.alter_column(T, "kind", existing_type=sa.String(40), nullable=True)
    for name, sql in TEMPLATE_CHECKS.items():
        _replace_check(name, sql, checks)
    if NAME_INDEX in indexes:
        op.drop_index(NAME_INDEX, table_name=T)
    op.create_index(NAME_INDEX, T, ["channel", sa.text("lower(name)")], unique=True, postgresql_where=sa.text("owner_user_id IS NULL"))
    if OWNER_INDEX not in indexes:
        op.create_index(OWNER_INDEX, T, ["owner_user_id", "channel", sa.text("lower(name)")], unique=True, postgresql_where=sa.text("owner_user_id IS NOT NULL"))
    if "ix_recruiter_message_templates_owner_user_id" not in indexes:
        op.create_index("ix_recruiter_message_templates_owner_user_id", T, ["owner_user_id"])
    if "recruiter_template_versions" not in tables:
        op.create_table(
            "recruiter_template_versions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("template_id", sa.Uuid(), sa.ForeignKey(f"{T}.id", ondelete="CASCADE"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("content", sa.JSON(), nullable=False),
            sa.Column("edited_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("template_id", "version", name="uq_recruiter_template_versions_version"),
        )
    op.execute(BACKFILL_CATEGORY)
    op.execute(BACKFILL_VERSIONS)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text(f"SELECT count(*) FROM {T} WHERE channel IN ('linkedin', 'call') OR owner_user_id IS NOT NULL")).scalar():
        raise RuntimeError("LinkedIn, calling-script or personal templates exist: 0120's schema cannot hold them")
    op.drop_table("recruiter_template_versions")
    op.add_column(T, sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.execute(f"UPDATE {T} SET active = (status = 'approved')")
    op.drop_index("ix_recruiter_message_templates_owner_user_id", table_name=T)
    op.drop_index(OWNER_INDEX, table_name=T)
    op.drop_index(NAME_INDEX, table_name=T)
    op.create_index(NAME_INDEX, T, ["channel", sa.text("lower(name)")], unique=True)
    for name in TEMPLATE_CHECKS:
        op.drop_constraint(name, T, type_="check")
    for name, sql in OLD_CHECKS.items():
        op.create_check_constraint(name, T, sql)
    op.create_check_constraint("ck_recruiter_message_templates_subject", T, TEMPLATE_CHECKS["ck_recruiter_message_templates_subject"])
    op.alter_column(T, "kind", existing_type=sa.String(40), nullable=False)
    for name, _ in reversed(COLUMNS):
        op.drop_column(T, name)
