"""pob-021 -- the submission record: each `profile_share_items` row gets a SUB- code, a status, consent, the match block and the
acknowledgement; `profile_shares` the compensation flag and the SLA follow-up; `companies` its SLA hours.

Revision ID: 0313_submissions
Revises: 0312_placements

docs/superpowers/specs/2026-11-08-pob-021-submission-record-design.md (DEC-SCOPE-430). Additive. 0001 builds a fresh database from the current
models, which already carry all of this, so each step runs only when missing. The CHECK strings are frozen copies of `models.SUBMISSION_CHECKS`,
`ck_profile_shares_recipient_detail` and `ck_companies_submission_sla`. Existing items keep their data: each gets the next SUB- code in creation
order and the status `submitted` (B1). The downgrade drops what the upgrade added and restores pob-011's detail rule.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0313_submissions"
down_revision = "0312_placements"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
SEQ = "profile_share_item_submission_seq"
CODE_DEFAULT = f"'SUB-' || lpad(nextval('{SEQ}')::text, 6, '0')"
STATUSES = ("submitted", "client_reviewing", "shortlisted", "interview", "rejected", "on_hold", "selected", "withdrawn")
REASONS = (
    "skills_mismatch", "experience_mismatch", "compensation_mismatch", "location_mismatch", "notice_period", "duplicate_submission",
    "position_filled", "client_not_interested", "candidate_withdrew", "other",
)  # fmt: skip


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


ITEM_CHECKS = {
    "ck_profile_share_items_status": _in("status", STATUSES),
    "ck_profile_share_items_rejection": f"(status = 'rejected') = (rejection_reason IS NOT NULL) AND (rejection_reason IS NULL OR {_in('rejection_reason', REASONS)})",
    "ck_profile_share_items_next_action": "next_action IS NULL OR char_length(next_action) <= 300",
    "ck_profile_share_items_consent": "consent_reference IS NULL OR char_length(consent_reference) <= 300",
}
DETAIL_NEW = "(recipient = 'client' AND detail IN ('named', 'anonymised')) OR (recipient = 'vendor' AND detail IN ('anonymised', 'full'))"
DETAIL_OLD = "(recipient = 'client') = (detail = 'named')"
SLA_CHECK = "submission_sla_hours IS NULL OR submission_sla_hours BETWEEN 1 AND 720"


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    item_columns = set() if offline else {c["name"] for c in inspector.get_columns("profile_share_items")}
    if offline or "submission_code" not in item_columns:
        op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ} MAXVALUE 999999")
        op.add_column("profile_share_items", sa.Column("submission_code", sa.String(20), nullable=True))
        # creation order by row_number (a per-row nextval in UPDATE ... FROM has no guaranteed order), then the sequence continues after it
        op.execute(
            "WITH o AS (SELECT id, row_number() OVER (ORDER BY created_at, id) AS n FROM profile_share_items) "
            "UPDATE profile_share_items i SET submission_code = 'SUB-' || lpad(o.n::text, 6, '0') FROM o WHERE o.id = i.id"
        )
        op.execute(f"SELECT setval('{SEQ}', GREATEST((SELECT count(*) FROM profile_share_items), 1), (SELECT count(*) FROM profile_share_items) > 0)")
        op.alter_column("profile_share_items", "submission_code", nullable=False, server_default=sa.text(CODE_DEFAULT))
        op.create_unique_constraint("uq_profile_share_items_submission_code", "profile_share_items", ["submission_code"])
        op.add_column("profile_share_items", sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'submitted'")))
        op.add_column("profile_share_items", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column("profile_share_items", sa.Column("rejection_reason", sa.String(30), nullable=True))
        op.add_column("profile_share_items", sa.Column("next_action", sa.Text(), nullable=True))
        op.add_column("profile_share_items", sa.Column("next_action_on", sa.Date(), nullable=True))
        op.add_column("profile_share_items", sa.Column("consent_reference", sa.Text(), nullable=True))
        op.add_column("profile_share_items", sa.Column("match", sa.JSON(), nullable=True))
        op.add_column("profile_share_items", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))
        for name, sql in ITEM_CHECKS.items():
            op.create_check_constraint(name, "profile_share_items", sql)
    share_columns = set() if offline else {c["name"] for c in inspector.get_columns("profile_shares")}
    if offline or "follow_up_id" not in share_columns:
        op.add_column("profile_shares", sa.Column("compensation_included", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        op.add_column("profile_shares", sa.Column("follow_up_id", UUID, sa.ForeignKey("recruiter_follow_ups.id", ondelete="SET NULL"), nullable=True))
        op.drop_constraint("ck_profile_shares_recipient_detail", "profile_shares", type_="check")
        op.create_check_constraint("ck_profile_shares_recipient_detail", "profile_shares", DETAIL_NEW)
    company_columns = set() if offline else {c["name"] for c in inspector.get_columns("companies")}
    if offline or "submission_sla_hours" not in company_columns:
        op.add_column("companies", sa.Column("submission_sla_hours", sa.Integer(), nullable=True))
        op.create_check_constraint("ck_companies_submission_sla", "companies", SLA_CHECK)


def downgrade() -> None:
    op.drop_constraint("ck_companies_submission_sla", "companies", type_="check")
    op.drop_column("companies", "submission_sla_hours")
    op.execute("UPDATE profile_shares SET detail = 'named' WHERE recipient = 'client'")
    op.drop_constraint("ck_profile_shares_recipient_detail", "profile_shares", type_="check")
    op.create_check_constraint("ck_profile_shares_recipient_detail", "profile_shares", DETAIL_OLD)
    op.drop_column("profile_shares", "follow_up_id")
    op.drop_column("profile_shares", "compensation_included")
    for name in ITEM_CHECKS:
        op.drop_constraint(name, "profile_share_items", type_="check")
    op.drop_constraint("uq_profile_share_items_submission_code", "profile_share_items", type_="unique")
    for column in ("acknowledged_at", "match", "consent_reference", "next_action_on", "next_action", "rejection_reason", "status_changed_at", "status", "submission_code"):
        op.drop_column("profile_share_items", column)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
