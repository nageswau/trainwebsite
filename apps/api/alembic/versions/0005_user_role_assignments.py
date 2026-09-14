"""Add user_role_assignments (FND-002, DATA_MODEL.md §1.1-1.3).

Revision ID: 0005_user_role_assignments
Revises: 0004_uuid_identifiers

Additive and backward-compatible: User.role/User.division are untouched, so every
existing route continues to work unmodified. Backfills one assignment per existing user
from those columns, matching what app.api.auth._sync_role_assignment does going forward
for new logins/registrations. Backfilled rows are all approval_status="approved" --
including any pre-existing "agent" rows -- so this migration never retroactively locks
out an account that already existed; only new agent registrations created after this
migration lands start "pending" (DATA_MODEL.md §1.3).

Like 0002/0003/0004 before it, this checks for an existing table first: 0001_initial's
Base.metadata.create_all() already creates every table current models.py defines
(including UserRoleAssignment, once added to app/models.py) on a fresh database, so this
migration's own op.create_table() only runs against a database that predates that model
existing at all -- the backfill INSERT, however, always runs (guarded by NOT EXISTS so
it's safe to run against either path).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_user_role_assignments"
down_revision = "0004_uuid_identifiers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_role_assignments" not in inspector.get_table_names():
        op.create_table(
            "user_role_assignments",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("division", sa.String(30), nullable=False),
            sa.Column("role", sa.String(50), nullable=False),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approval_status", sa.String(20), nullable=False, server_default="approved"),
            sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rejection_reason", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "division", "role", name="uq_role_assignment_identity"),
        )
        op.create_index("ix_user_role_assignments_user_id", "user_role_assignments", ["user_id"])
        op.create_index("ix_user_role_assignments_division", "user_role_assignments", ["division"])
        op.create_index("ix_user_role_assignments_role", "user_role_assignments", ["role"])

    if bind.dialect.name == "postgresql" and "users" in inspector.get_table_names():
        bind.execute(sa.text(
            "INSERT INTO user_role_assignments "
            "(id, user_id, division, role, is_active, assigned_at, approval_status, created_at, updated_at) "
            "SELECT gen_random_uuid(), account.id, account.division, account.role, true, account.created_at, 'approved', now(), now() "
            "FROM users AS account "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM user_role_assignments AS existing "
            "  WHERE existing.user_id = account.id AND existing.division = account.division AND existing.role = account.role"
            ")"
        ))


def downgrade() -> None:
    op.drop_index("ix_user_role_assignments_role", table_name="user_role_assignments")
    op.drop_index("ix_user_role_assignments_division", table_name="user_role_assignments")
    op.drop_index("ix_user_role_assignments_user_id", table_name="user_role_assignments")
    op.drop_table("user_role_assignments")
