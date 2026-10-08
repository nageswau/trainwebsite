"""rec-026 -- recruiter_message_templates (+ 12 seeds, one per EVID-018 §19 kind) and recruiter_messages.

Revision ID: 0120_recruiter_messages
Revises: 0119_recruiter_meetings

docs/superpowers/specs/2026-10-08-rec-026-recruiter-messages-design.md §2 (DEC-SCOPE-135). Two new tables; no existing row changes.
0001 builds a fresh database from the current models, which already carry these tables, so creation is guarded (0110's idiom) -- but the
seed always runs and inserts only a (channel, name) that is missing, so it is idempotent and never overwrites a manager's edit.
The kinds and CHECKS repeat app.models (test_rec_026_migration). downgrade() refuses while any message exists or any template is not
exactly its seed: entered data is never dropped silently.

Re-chained 2026-10-08 on merging `main` @ `7852882f`: drafted as `0120` on `0117_job_descriptions`, briefly `0119` on rec-025's
`0118_recruiter_calls`; rec-028 (`0119_recruiter_meetings`, DEC-SCOPE-134) merged first, so this is `0120` on it (DEC-SCOPE-135, API §12BC,
RBAC §2.61). A database stamped at a draft is re-stamped with `alembic stamp --purge 0118_recruiter_calls` (or `0117_job_descriptions`), then
`upgrade head` (every table step is guarded and the seed is idempotent).
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0120_recruiter_messages"
down_revision = "0119_recruiter_meetings"
branch_labels = None
depends_on = None

TEMPLATES, MESSAGES = "recruiter_message_templates", "recruiter_messages"
UUID = postgresql.UUID(as_uuid=True)
WHATSAPP_KINDS = ("candidate_profiles", "jd_confirmation", "interview_reminder", "follow_up", "requirement_update")
EMAIL_KINDS = (
    "company_introduction",
    "recruitment_proposal",
    "candidate_profiles",
    "jd_acknowledgement",
    "interview_confirmation",
    "offer_follow_up",
    "joining_confirmation",
)
TEMPLATE_CHECKS = {  # must equal app.models.RECRUITER_TEMPLATE_CHECKS
    "ck_recruiter_message_templates_channel": "channel IN ('whatsapp', 'email')",
    "ck_recruiter_message_templates_kind": (
        f"(channel = 'whatsapp' AND kind IN ({', '.join(repr(k) for k in WHATSAPP_KINDS)})) OR (channel = 'email' AND kind IN ({', '.join(repr(k) for k in EMAIL_KINDS)}))"
    ),
    "ck_recruiter_message_templates_subject": "(channel = 'email') = (subject IS NOT NULL)",
}
MESSAGE_CHECKS = {  # must equal app.models.RECRUITER_MESSAGE_CHECKS
    "ck_recruiter_messages_party": "(contact_id IS NULL) = (company_id IS NULL) AND (contact_id IS NULL) <> (candidate_id IS NULL)",
    "ck_recruiter_messages_channel": "channel IN ('whatsapp', 'email')",
    "ck_recruiter_messages_email": "(channel = 'email') = (delivery_status IS NOT NULL) AND (channel = 'email') = (subject IS NOT NULL)",
    "ck_recruiter_messages_status": "delivery_status IS NULL OR delivery_status IN ('queued', 'sending', 'retrying', 'sent', 'failed')",
}
MESSAGE_INDEXES = {
    "ix_recruiter_messages_company_sent": ["company_id", "sent_at"],
    "ix_recruiter_messages_contact_sent": ["contact_id", "sent_at"],
    "ix_recruiter_messages_candidate_sent": ["candidate_id", "sent_at"],
    "ix_recruiter_messages_sender_sent": ["sender_user_id", "sent_at"],
}


def _seed(channel: str, kind: str, name: str, body: str, subject: str | None = None) -> dict:
    return {"channel": channel, "kind": kind, "name": name, "subject": subject, "body": body}


# AC1 (MS1, MS2): one template per source kind, named after its source label, written with the placeholders.
SEED = (
    _seed(
        "whatsapp",
        "candidate_profiles",
        "Candidate profiles",
        "Hi {name}, this is {recruiter} from EduSphere. I have shared candidate profiles for {company}'s open roles. Please review them and let me know whom you would like to interview.",
    ),
    _seed(
        "whatsapp",
        "jd_confirmation",
        "JD confirmation",
        "Hi {name}, this is {recruiter} from EduSphere. Could you please confirm the job description for {company}'s requirement so we can start sourcing?",
    ),
    _seed(
        "whatsapp",
        "interview_reminder",
        "Interview reminders",
        "Hi {name}, a reminder about your interview with {company}. Please be on time and keep your resume ready. All the best! – {recruiter}, EduSphere",
    ),
    _seed("whatsapp", "follow_up", "Follow-up", "Hi {name}, this is {recruiter} from EduSphere, following up on our last conversation. Please let me know a good time to talk."),
    _seed("whatsapp", "requirement_update", "Requirement updates", "Hi {name}, this is {recruiter} from EduSphere. Do you have any new openings or updates to {company}'s current requirements?"),
    _seed(
        "email",
        "company_introduction",
        "Company introduction",
        "Dear {name},\n\nI am {recruiter} from EduSphere's recruitment team. We help companies like {company} hire trained, job-ready candidates across IT and non-IT roles.\n\nI would welcome a short call to understand your hiring plans.\n\nRegards,\n{recruiter}",
        "EduSphere recruitment services for {company}",
    ),
    _seed(
        "email",
        "recruitment_proposal",
        "Recruitment proposal",
        "Dear {name},\n\nThank you for your time. As discussed, please find below our recruitment proposal for {company}: dedicated sourcing, screened shortlists and interview coordination.\n\nI am happy to walk you through the commercial terms.\n\nRegards,\n{recruiter}",
        "Recruitment proposal for {company}",
    ),
    _seed(
        "email",
        "candidate_profiles",
        "Candidate profiles",
        "Dear {name},\n\nI am sharing candidate profiles for {company}'s open roles. Please review them and let me know whom you would like to interview.\n\nRegards,\n{recruiter}",
        "Candidate profiles for {company}",
    ),
    _seed(
        "email",
        "jd_acknowledgement",
        "JD acknowledgement",
        "Dear {name},\n\nThank you for sharing the job description. We have started sourcing for {company} and will send matching profiles shortly.\n\nRegards,\n{recruiter}",
        "Job description received – {company}",
    ),
    _seed(
        "email",
        "interview_confirmation",
        "Interview confirmation",
        "Dear {name},\n\nYour interview with {company} is confirmed. Please carry an updated resume and join on time. Reply to this email if you need to reschedule.\n\nAll the best,\n{recruiter}",
        "Interview confirmation – {company}",
    ),
    _seed(
        "email",
        "offer_follow_up",
        "Offer follow-up",
        "Dear {name},\n\nI am following up on the offer from {company}. Please let me know your decision or any questions you have.\n\nRegards,\n{recruiter}",
        "Your offer from {company}",
    ),
    _seed(
        "email",
        "joining_confirmation",
        "Joining confirmation",
        "Dear {name},\n\nPlease confirm your joining date with {company}. Congratulations once again, and do reach out if you need anything.\n\nRegards,\n{recruiter}",
        "Joining confirmation – {company}",
    ),
)


def seed_statements() -> list[tuple[str, dict]]:
    """Each seed is inserted only when no template of its channel has its name (case-insensitive)."""
    sql = (
        f"INSERT INTO {TEMPLATES} (id, channel, kind, name, subject, body, active, created_at, updated_at) "
        "SELECT :id, CAST(:channel AS VARCHAR), :kind, CAST(:name AS VARCHAR), :subject, :body, true, now(), now() "
        f"WHERE NOT EXISTS (SELECT 1 FROM {TEMPLATES} WHERE channel = CAST(:channel AS VARCHAR) AND lower(name) = lower(CAST(:name AS VARCHAR)))"
    )
    return [(sql, {"id": uuid.uuid4(), **seed}) for seed in SEED]


def upgrade() -> None:
    if op.get_context().as_sql or TEMPLATES not in sa.inspect(op.get_bind()).get_table_names():
        when = sa.DateTime(timezone=True)

        def stamps():
            return (sa.Column("created_at", when, server_default=sa.func.now(), nullable=False), sa.Column("updated_at", when, server_default=sa.func.now(), nullable=False))

        def fk(target: str):
            return sa.ForeignKey(target, ondelete="RESTRICT")

        op.create_table(
            TEMPLATES,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column("kind", sa.String(40), nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("subject", sa.String(200), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            *stamps(),
            *(sa.CheckConstraint(sql, name=name) for name, sql in TEMPLATE_CHECKS.items()),
        )
        op.create_index("uq_recruiter_message_templates_channel_name", TEMPLATES, ["channel", sa.text("lower(name)")], unique=True)
        op.create_table(
            MESSAGES,
            sa.Column("id", UUID, primary_key=True),
            sa.Column("company_id", UUID, fk("companies.id"), nullable=True),
            sa.Column("contact_id", UUID, fk("company_contacts.id"), nullable=True),
            sa.Column("candidate_id", UUID, fk("candidates.id"), nullable=True),
            sa.Column("sender_user_id", UUID, fk("users.id"), nullable=False),
            sa.Column("channel", sa.String(16), nullable=False),
            sa.Column("template_id", UUID, fk(f"{TEMPLATES}.id"), nullable=True),
            sa.Column("template_name", sa.String(160), nullable=True),
            sa.Column("subject", sa.String(200), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("delivery_status", sa.String(16), nullable=True),
            sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("sent_at", when, nullable=False),
            *stamps(),
            *(sa.CheckConstraint(sql, name=name) for name, sql in MESSAGE_CHECKS.items()),
        )
        for name, columns in MESSAGE_INDEXES.items():
            op.create_index(name, MESSAGES, columns)
    for statement, params in seed_statements():
        op.execute(sa.text(statement).bindparams(**params))


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        stored = {tuple(r) for r in bind.execute(sa.text(f"SELECT channel, kind, name, subject, body, active FROM {TEMPLATES}")).all()}
        seeded = {(s["channel"], s["kind"], s["name"], s["subject"], s["body"], True) for s in SEED}
        if bind.execute(sa.text(f"SELECT 1 FROM {MESSAGES} LIMIT 1")).first() or stored != seeded:
            raise RuntimeError("Cannot downgrade 0120_recruiter_messages: recruiter messages or edited templates exist. Clear them deliberately first.")
    op.drop_table(MESSAGES)
    op.drop_table(TEMPLATES)
