"""hrc-028 -- the interview fields (round number, end, time zone, platform, phone, instructions, documents, cancel reason, calendar
sequence), the `cancelled` status, the `details` event with the old and new link/location, and the invite text on a recruiter email.

Revision ID: 0274_interview_completion
Revises: 0273_candidate_privacy

docs/superpowers/specs/2026-11-05-hrc-028-interview-completion-design.md (DEC-SCOPE-398). 0001 builds a fresh database from the current
models, which already carry the columns, so each column/check is added only when missing (0222's idiom); the status and event CHECKs
always replace rec-020's (0133) copies. Every constant is a frozen copy of the models at this revision (test_hrc_028_migration). No
backfill: every existing row keeps NULLs, `time_zone` defaults to Asia/Kolkata and `calendar_sequence` to 0. The downgrade restores
0133's CHECKs, so it fails while a cancelled interview or a `details` event exists.
"""

import sqlalchemy as sa

from alembic import op

revision = "0274_interview_completion"
down_revision = "0273_candidate_privacy"
branch_labels = None
depends_on = None

STATUSES = ("scheduled", "confirmed", "completed", "rescheduled", "no_show", "selected", "rejected", "on_hold", "cancelled")
EVENTS = ("scheduled", "rescheduled", "status", "details")
PLATFORMS = ("google_meet", "microsoft_teams", "zoom", "zoho_meeting", "other")
OLD_STATUSES = STATUSES[:-1]
OLD_EVENTS = EVENTS[:-1]


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


STATUS_CHECK = ("ck_interviews_status", f"status IN ({_in(STATUSES)})")
EVENT_CHECK = ("ck_interview_events_event", f"event IN ({_in(EVENTS)})")
CHECKS = {
    "ck_interviews_round_number": "round_number IS NULL OR round_number BETWEEN 1 AND 20",
    "ck_interviews_platform": f"platform IS NULL OR platform IN ({_in(PLATFORMS)})",
    "ck_interviews_ends_after_start": "ends_at IS NULL OR (ends_at > scheduled_at AND ends_at <= scheduled_at + interval '12 hours')",
    "ck_interviews_cancel_reason": "(status = 'cancelled') = (cancel_reason IS NOT NULL)",
}
COLUMNS = (
    ("round_number", sa.SmallInteger()), ("ends_at", sa.DateTime(timezone=True)), ("platform", sa.String(20)), ("phone_details", sa.String(200)),
    ("instructions", sa.String(2000)), ("documents_required", sa.String(1000)), ("cancel_reason", sa.String(500)),
)  # fmt: skip
EVENT_COLUMNS = (("old_meeting_url", 500), ("new_meeting_url", 500), ("old_location", 200), ("new_location", 200))


def _existing(table: str, offline: bool) -> tuple[set, set]:
    if offline:
        return set(), set()
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)}, {c["name"] for c in inspector.get_check_constraints(table)}


def _replace_check(table: str, name: str, sql: str, offline: bool) -> None:
    if offline or name in _existing(table, offline)[1]:
        op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, sql)


def upgrade() -> None:
    offline = op.get_context().as_sql
    columns, checks = _existing("interviews", offline)
    for name, kind in COLUMNS:
        if name not in columns:
            op.add_column("interviews", sa.Column(name, kind, nullable=True))
    if "time_zone" not in columns:
        op.add_column("interviews", sa.Column("time_zone", sa.String(64), nullable=False, server_default="Asia/Kolkata"))
    if "calendar_sequence" not in columns:
        op.add_column("interviews", sa.Column("calendar_sequence", sa.Integer(), nullable=False, server_default="0"))
    _replace_check("interviews", *STATUS_CHECK, offline)
    for name, sql in CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "interviews", sql)
    event_columns, _ = _existing("interview_events", offline)
    for name, length in EVENT_COLUMNS:
        if name not in event_columns:
            op.add_column("interview_events", sa.Column(name, sa.String(length), nullable=True))
    _replace_check("interview_events", *EVENT_CHECK, offline)
    if "calendar_ics" not in _existing("recruiter_messages", offline)[0]:
        op.add_column("recruiter_messages", sa.Column("calendar_ics", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("recruiter_messages", "calendar_ics")
    _replace_check("interview_events", "ck_interview_events_event", f"event IN ({_in(OLD_EVENTS)})", False)
    for name, _length in EVENT_COLUMNS:
        op.drop_column("interview_events", name)
    for name in CHECKS:
        op.drop_constraint(name, "interviews", type_="check")
    _replace_check("interviews", "ck_interviews_status", f"status IN ({_in(OLD_STATUSES)})", False)
    for name in ("calendar_sequence", "time_zone", *(n for n, _ in COLUMNS)):
        op.drop_column("interviews", name)
