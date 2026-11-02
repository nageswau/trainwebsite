"""itc-019 -- trainer profiles (designation, expertise, bio, office hours, contact route, per-field visibility, photo key).

Revision ID: 0230_trainer_profiles
Revises: 0229_it_student_profiles

docs/superpowers/specs/2026-11-02-itc-019-faculty-profiles-design.md (DEC-SCOPE-346). One new table; nothing existing changes (the free
text `programs.trainer_name` stays). 0001 builds a fresh database from the current models, which already carry it, so the upgrade is
guarded (0222's idiom). The downgrade refuses while a profile exists, so it never silently drops one.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0230_trainer_profiles"
down_revision = "0229_it_student_profiles"
branch_labels = None
depends_on = None

TABLE = "trainer_profiles"


def upgrade() -> None:
    if not op.get_context().as_sql and TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("designation", sa.String(120), nullable=True),
        sa.Column("expertise", sa.JSON, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("office_hours", sa.String(160), nullable=True),
        sa.Column("contact_route", sa.String(10), nullable=False, server_default="in_app"),
        sa.Column("show_email", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("show_phone", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("show_photo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("show_bio", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("show_office_hours", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("photo_key", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("contact_route IN ('in_app', 'email', 'phone')", name="ck_trainer_profiles_contact_route"),
    )


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {TABLE} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0230: trainer profiles exist (itc-019)")
    op.drop_table(TABLE)
