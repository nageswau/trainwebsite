"""pob-015 -- vacancies shared with institutions (DEC-SCOPE-426 V1-V6).

Revision ID: 0307_institution_vacancy_shares
Revises: 0306_institution_student_pool

docs/superpowers/specs/2026-11-07-pob-015-vacancy-sharing-campus-design.md. Additive only: one new table; no existing row changes. 0001
runs `create_all` from today's models, so a fresh database already has it: the step runs only when missing. CHECKS is a frozen copy of
`models.VACANCY_SHARE_CHECKS`. The downgrade drops what the upgrade added.
"""

import sqlalchemy as sa

from alembic import op

revision = "0307_institution_vacancy_shares"
down_revision = "0306_institution_student_pool"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_institution_vacancy_shares_channel": "channel IN ('meeting', 'call', 'email', 'whatsapp', 'visit', 'other')",
    "ck_institution_vacancy_shares_response": "response IN ('awaiting', 'interested', 'declined', 'no_response')",
}
TABLE = "institution_vacancy_shares"


def _user(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("shared_on", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("template_id", sa.Uuid(), sa.ForeignKey("recruiter_message_templates.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("response", sa.String(12), server_default=sa.text("'awaiting'"), nullable=False),
        sa.Column("response_note", sa.String(500), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        _user("responded_by_user_id", nullable=True),
        _user("shared_by_user_id"),
        *(sa.Column(n, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False) for n in ("created_at", "updated_at")),
        *(sa.CheckConstraint(sql, name=name) for name, sql in CHECKS.items()),
        sa.UniqueConstraint("organization_id", "job_id", "shared_on", "channel", name="uq_institution_vacancy_shares_once"),
    )
    op.create_index("ix_institution_vacancy_shares_org_day", TABLE, ["organization_id", "shared_on"])
    op.create_index("ix_institution_vacancy_shares_job", TABLE, ["job_id"])


def downgrade() -> None:
    op.drop_table(TABLE)
