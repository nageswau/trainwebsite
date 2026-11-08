"""pob-011 -- vendor requirements, vendor submissions and candidate-visibility control (DEC-SCOPE-427 V2-V7, V11).

Revision ID: 0308_vendor_requirements
Revises: 0307_institution_vacancy_shares

docs/superpowers/specs/2026-11-08-pob-011-vendor-requirements-submissions-design.md. Additive only:
- `jobs.via_vendor_id` and `jobs.end_client_disclosure` (existing jobs read `external`, today's behaviour)
- `profile_shares.recipient`, `detail` and `consent_reference` (existing shares read `client` / `named`)

0001 runs `create_all` from today's models, so a fresh database already has every column, index and CHECK: each step runs only when
missing. JOB_CHECKS and SHARE_CHECKS are frozen copies of `models.JOB_VENDOR_CHECKS` and `models.PROFILE_SHARE_VENDOR_CHECKS`. The
downgrade drops what the upgrade added.
"""

import sqlalchemy as sa

from alembic import op

revision = "0308_vendor_requirements"
down_revision = "0307_institution_vacancy_shares"
branch_labels = None
depends_on = None

JOB_CHECKS = {
    "ck_jobs_end_client_disclosure": "end_client_disclosure IN ('external', 'internal')",
    "ck_jobs_via_vendor_not_self": "via_vendor_id IS NULL OR via_vendor_id <> company_id",
}
SHARE_CHECKS = {
    "ck_profile_shares_recipient": "recipient IN ('client', 'vendor')",
    "ck_profile_shares_detail": "detail IN ('named', 'anonymised', 'full')",
    "ck_profile_shares_recipient_detail": "(recipient = 'client') = (detail = 'named')",
    "ck_profile_shares_vendor_channel": "recipient = 'client' OR channel <> 'portal'",
    "ck_profile_shares_consent": "(detail = 'full') = (consent_reference IS NOT NULL) AND (consent_reference IS NULL OR char_length(consent_reference) <= 300)",
}
JOB_INDEX = "ix_jobs_via_vendor"
JOB_FK = "fk_jobs_via_vendor_id_companies"


def _inspect():
    return sa.inspect(op.get_bind())


def _add_columns(table: str, columns: list[sa.Column]) -> None:
    present = {c["name"] for c in _inspect().get_columns(table)}
    for column in columns:
        if column.name not in present:
            op.add_column(table, column)


def _add_checks(table: str, checks: dict[str, str]) -> None:
    present = {c["name"] for c in _inspect().get_check_constraints(table)}
    for name, sql in checks.items():
        if name not in present:
            op.create_check_constraint(name, table, sql)


def upgrade() -> None:
    _add_columns("jobs", [
        sa.Column("via_vendor_id", sa.Uuid(), nullable=True),
        sa.Column("end_client_disclosure", sa.String(10), nullable=False, server_default="external"),
    ])  # fmt: skip
    inspector = _inspect()
    if not any(fk["constrained_columns"] == ["via_vendor_id"] for fk in inspector.get_foreign_keys("jobs")):
        op.create_foreign_key(JOB_FK, "jobs", "companies", ["via_vendor_id"], ["id"], ondelete="RESTRICT")
    if JOB_INDEX not in {i["name"] for i in inspector.get_indexes("jobs")}:
        op.create_index(JOB_INDEX, "jobs", ["via_vendor_id"])
    _add_checks("jobs", JOB_CHECKS)
    _add_columns("profile_shares", [
        sa.Column("recipient", sa.String(10), nullable=False, server_default="client"),
        sa.Column("detail", sa.String(12), nullable=False, server_default="named"),
        sa.Column("consent_reference", sa.Text(), nullable=True),
    ])  # fmt: skip
    _add_checks("profile_shares", SHARE_CHECKS)


def downgrade() -> None:
    for name in SHARE_CHECKS:
        op.drop_constraint(name, "profile_shares", type_="check")
    for column in ("consent_reference", "detail", "recipient"):
        op.drop_column("profile_shares", column)
    for name in JOB_CHECKS:
        op.drop_constraint(name, "jobs", type_="check")
    op.drop_index(JOB_INDEX, table_name="jobs")
    fk = next((fk["name"] for fk in _inspect().get_foreign_keys("jobs") if fk["constrained_columns"] == ["via_vendor_id"]), None)
    if fk:
        op.drop_constraint(fk, "jobs", type_="foreignkey")
    op.drop_column("jobs", "end_client_disclosure")
    op.drop_column("jobs", "via_vendor_id")
