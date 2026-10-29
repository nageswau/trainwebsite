"""nehn-017 -- HR's student grants: `student_progress`, `attendance` and `student_documents` (view, download) for hr_team.

Revision ID: 0216_hr_student_grants
Revises: 0215_payment_discount_ledger

docs/superpowers/specs/2026-10-28-nehn-017-hr-student-access-design.md (DEC-SCOPE-310 H3). Seed only: SEED is a frozen copy of the new
`rbac.DEFAULT_GRANTS["hr_team"]` keys at this revision. A row that is already there (re-run) is left alone; no existing row changes. The
downgrade deletes every grant and override of the three resources.
"""

import sqlalchemy as sa

from alembic import op

revision = "0216_hr_student_grants"
down_revision = "0215_payment_discount_ledger"
branch_labels = None
depends_on = None

RESOURCES = ("student_progress", "attendance", "student_documents")
SEED = tuple(("hr_team", resource, action) for resource in RESOURCES for action in ("view", "download"))


def upgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    op.execute("DELETE FROM user_permission_overrides WHERE resource IN ('student_progress', 'attendance', 'student_documents')")
    op.execute("DELETE FROM role_permissions WHERE resource IN ('student_progress', 'attendance', 'student_documents')")
