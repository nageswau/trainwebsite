"""bdm-019 -- agent onboarding handover: the Agent Organization link and agent requests.

Revision ID: 0095_bdm_agent_link
Revises: 0094_bdm_daily_reports

docs/superpowers/specs/2026-10-07-bdm-019-agent-onboarding-handover-design.md §3 (DEC-SCOPE-100). Two nullable FK columns
(`bdm_organizations.agent_org_id`, unique; `bdm_onboarding_requests.agent_org_id`) and three CHECKs replaced or added, so a request may
be for an Agent organization and complete with an agency. No row is read or written: every existing request is a School one with no
agency, which the new CHECKs accept. 0001 builds a fresh database from the current models, which already carry all of it, so each step is
guarded. CHECKS must stay a subset of app.models.BDM_ONBOARDING_CHECKS (test_bdm_019_migration). downgrade() refuses while any agent
request or agent link exists, then restores 0084's rules.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0095_bdm_agent_link"
down_revision = "0094_bdm_daily_reports"
branch_labels = None
depends_on = None

REQUESTS = "bdm_onboarding_requests"
ORGS = "bdm_organizations"
LINK_UNIQUE = "uq_bdm_organizations_agent_org"
CHECKS = {
    "ck_bdm_onboarding_requests_kind": "kind IN ('school', 'agent')",
    "ck_bdm_onboarding_requests_completed": "status <> 'completed' OR (resolution IS NOT NULL AND (school_id IS NOT NULL OR agent_org_id IS NOT NULL))",
    "ck_bdm_onboarding_requests_target": "(kind = 'school' AND agent_org_id IS NULL) OR (kind = 'agent' AND school_id IS NULL)",
}
# 0084's strings, restored by downgrade (the target CHECK did not exist).
SCHOOL_ONLY = {
    "ck_bdm_onboarding_requests_kind": "kind IN ('school')",
    "ck_bdm_onboarding_requests_completed": "status <> 'completed' OR (school_id IS NOT NULL AND resolution IS NOT NULL)",
}


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def _columns(inspector, table: str) -> set[str]:
    return set() if inspector is None else {c["name"] for c in inspector.get_columns(table)}


def _checks(inspector) -> dict[str, str]:
    return {} if inspector is None else {c["name"]: c["sqltext"] for c in inspector.get_check_constraints(REQUESTS)}


def upgrade() -> None:
    inspector = _inspector()
    uuid = postgresql.UUID(as_uuid=True)
    if "agent_org_id" not in _columns(inspector, ORGS):
        op.add_column(ORGS, sa.Column("agent_org_id", uuid, sa.ForeignKey("agent_orgs.id", ondelete="RESTRICT"), nullable=True))
        op.create_unique_constraint(LINK_UNIQUE, ORGS, ["agent_org_id"])
    if "agent_org_id" not in _columns(inspector, REQUESTS):
        op.add_column(REQUESTS, sa.Column("agent_org_id", uuid, sa.ForeignKey("agent_orgs.id", ondelete="RESTRICT"), nullable=True))
    existing = _checks(inspector)
    for name, sql in CHECKS.items():
        if inspector is not None and name in existing and "agent" in existing[name]:
            continue  # a fresh database built from the models already has the widened rule
        if name in existing or (inspector is None and name in SCHOOL_ONLY):
            op.drop_constraint(name, REQUESTS, type_="check")
        op.create_check_constraint(name, REQUESTS, sql)


def downgrade() -> None:
    if not op.get_context().as_sql:
        bind = op.get_bind()
        if bind.execute(sa.text(f"SELECT 1 FROM {REQUESTS} WHERE kind <> 'school' LIMIT 1")).first() or bind.execute(sa.text(f"SELECT 1 FROM {ORGS} WHERE agent_org_id IS NOT NULL LIMIT 1")).first():
            raise RuntimeError("Cannot downgrade 0095_bdm_agent_link: agent onboarding data exists. Clear it deliberately first.")
    for name in CHECKS:
        op.drop_constraint(name, REQUESTS, type_="check")
    for name, sql in SCHOOL_ONLY.items():
        op.create_check_constraint(name, REQUESTS, sql)
    op.drop_column(REQUESTS, "agent_org_id")
    op.drop_constraint(LINK_UNIQUE, ORGS, type_="unique")
    op.drop_column(ORGS, "agent_org_id")
