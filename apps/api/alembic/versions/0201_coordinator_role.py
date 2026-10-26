"""nehn-030 -- the coordinator's day-one grant: `certificates.view` in `role_permissions`.

Revision ID: 0201_coordinator_role
Revises: 0200_submission_files

docs/superpowers/specs/2026-10-26-nehn-030-coordinator-role-design.md (DEC-SCOPE-293). The role itself needs no schema change (`users.role`
is a free string). SEED is a frozen copy of `rbac.DEFAULT_GRANTS["coordinator"]` at this revision; a row that is already there (re-run) is
left alone. No existing row changes. The downgrade deletes only these rows.
"""

import sqlalchemy as sa

from alembic import op

revision = "0201_coordinator_role"
down_revision = "0200_submission_files"
branch_labels = None
depends_on = None

SEED = (("coordinator", "certificates", "view"),)


def upgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("INSERT INTO role_permissions (role, resource, action) VALUES (:role, :resource, :action) ON CONFLICT DO NOTHING").bindparams(role=role, resource=resource, action=action))


def downgrade() -> None:
    for role, resource, action in SEED:
        op.execute(sa.text("DELETE FROM role_permissions WHERE role = :role AND resource = :resource AND action = :action").bindparams(role=role, resource=resource, action=action))
