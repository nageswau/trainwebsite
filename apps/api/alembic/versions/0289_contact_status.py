"""pob-005 -- contact status, decision-maker, source/verification and logged replies (DEC-SCOPE-411 D1-D8).

Revision ID: 0289_contact_status
Revises: 0288_college_placement

docs/superpowers/specs/2026-11-05-pob-005-contact-status-design.md. Additive: five `company_contacts` columns with their CHECKs, the
LinkedIn preferred channel (the channel CHECK is widened), an email index for the duplicate check, and `recruiter_messages.replied_at`.
Every step is guarded (0001's `create_all` already builds today's models on a fresh database). `status` is backfilled from existing
activity (BACKFILL), nothing else is rewritten. STATUSES, SOURCES and CHECKS are frozen copies of the models' values. The downgrade clears
LinkedIn channels (the old CHECK cannot hold them) and drops what the upgrade added.
"""

import sqlalchemy as sa

from alembic import op

revision = "0289_contact_status"
down_revision = "0288_college_placement"
branch_labels = None
depends_on = None

STATUSES = ("not_contacted", "contacted", "replied", "meeting_scheduled", "not_interested", "do_not_contact")
SOURCES = ("linkedin", "company_website", "referral", "job_portal", "event", "inbound", "other")
CHANNELS = ("call", "whatsapp", "email", "linkedin")
OLD_CHANNELS = ("call", "whatsapp", "email")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


CHECKS = {
    "ck_company_contacts_channel": f"preferred_channel IS NULL OR {_in('preferred_channel', CHANNELS)}",
    "ck_company_contacts_source": f"source IS NULL OR {_in('source', SOURCES)}",
    "ck_company_contacts_status": _in("status", STATUSES),
}
# The furthest automatic status each contact's existing activity reached (design D4 order); a cancelled meeting does not count.
BACKFILL = """
UPDATE company_contacts c SET status = CASE
    WHEN EXISTS (SELECT 1 FROM recruiter_meetings m WHERE m.contact_id = c.id AND m.status <> 'cancelled')
      OR EXISTS (SELECT 1 FROM recruiter_meeting_participants p JOIN recruiter_meetings m ON m.id = p.meeting_id
                 WHERE p.contact_id = c.id AND m.status <> 'cancelled') THEN 'meeting_scheduled'
    WHEN EXISTS (SELECT 1 FROM recruiter_calls k WHERE k.contact_id = c.id AND (k.direction = 'incoming' OR k.outcome = 'connected')) THEN 'replied'
    WHEN EXISTS (SELECT 1 FROM recruiter_calls k WHERE k.contact_id = c.id)
      OR EXISTS (SELECT 1 FROM recruiter_messages r WHERE r.contact_id = c.id)
      OR EXISTS (SELECT 1 FROM profile_shares s WHERE s.contact_id = c.id) THEN 'contacted'
    ELSE 'not_contacted' END
WHERE c.status = 'not_contacted'
"""


def _existing() -> tuple[set, set, set, set]:
    if op.get_context().as_sql:
        return set(), set(), set(), set()
    inspector = sa.inspect(op.get_bind())
    return (
        {c["name"] for c in inspector.get_columns("company_contacts")},
        {c["name"] for c in inspector.get_check_constraints("company_contacts")},
        {i["name"] for i in inspector.get_indexes("company_contacts")},
        {c["name"] for c in inspector.get_columns("recruiter_messages")},
    )


def upgrade() -> None:
    columns, checks, indexes, message_columns = _existing()
    added_status = "status" not in columns
    if "is_decision_maker" not in columns:
        op.add_column("company_contacts", sa.Column("is_decision_maker", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "source" not in columns:
        op.add_column("company_contacts", sa.Column("source", sa.String(32), nullable=True))
    if "verified_on" not in columns:
        op.add_column("company_contacts", sa.Column("verified_on", sa.Date(), nullable=True))
    if added_status:
        op.add_column("company_contacts", sa.Column("status", sa.String(24), nullable=False, server_default=sa.text("'not_contacted'")))
    if "status_changed_at" not in columns:
        op.add_column("company_contacts", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))
    if "ck_company_contacts_channel" in checks:
        op.drop_constraint("ck_company_contacts_channel", "company_contacts", type_="check")
    for name, sql in CHECKS.items():
        if name == "ck_company_contacts_channel" or name not in checks:
            op.create_check_constraint(name, "company_contacts", sql)
    if "ix_company_contacts_email" not in indexes:
        op.create_index("ix_company_contacts_email", "company_contacts", ["email"])
    if "replied_at" not in message_columns:
        op.add_column("recruiter_messages", sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True))
    if added_status:
        op.execute(BACKFILL)


def downgrade() -> None:
    op.drop_column("recruiter_messages", "replied_at")
    op.drop_index("ix_company_contacts_email", table_name="company_contacts")
    for name in CHECKS:
        op.drop_constraint(name, "company_contacts", type_="check")
    op.execute("UPDATE company_contacts SET preferred_channel = NULL WHERE preferred_channel = 'linkedin'")
    op.create_check_constraint("ck_company_contacts_channel", "company_contacts", f"preferred_channel IS NULL OR {_in('preferred_channel', OLD_CHANNELS)}")
    for column in ("status_changed_at", "status", "verified_on", "source", "is_decision_maker"):
        op.drop_column("company_contacts", column)
