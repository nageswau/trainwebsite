"""Add career_paths and real_projects (PUB-001: PRD-PUB-004/PRD-PUB-005).

Revision ID: 0006_public_content_collections
Revises: 0005_user_role_assignments

Business Services (PRD-PUB-007) and Success Stories (PRD-PUB-006) reuse the existing
ContentPage/Testimonial models -- no schema change needed for those two. Career Paths
and Real Projects need structured, multi-item collections with their own detail view
(skills/related-courses/outcomes; tech stack/description), which neither existing model
supports, so they get dedicated tables here.

Like 0002-0005 before it: checks for an existing table first, since 0001_initial's
Base.metadata.create_all() already creates every table current models.py defines on a
fresh database.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_public_content_collections"
down_revision = "0005_user_role_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = inspector.get_table_names()

    if "career_paths" not in existing:
        op.create_table(
            "career_paths",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("division", sa.String(30), nullable=False, server_default="it"),
            sa.Column("slug", sa.String(160), nullable=False, unique=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("summary", sa.Text, nullable=False),
            sa.Column("skills", postgresql.JSON, nullable=False, server_default="[]"),
            sa.Column("related_program_slugs", postgresql.JSON, nullable=False, server_default="[]"),
            sa.Column("outcomes", sa.Text, nullable=False),
            sa.Column("published", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_career_paths_division", "career_paths", ["division"])
        op.create_index("ix_career_paths_slug", "career_paths", ["slug"], unique=True)

    if "real_projects" not in existing:
        op.create_table(
            "real_projects",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("division", sa.String(30), nullable=False, server_default="it"),
            sa.Column("slug", sa.String(160), nullable=False, unique=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("summary", sa.Text, nullable=False),
            sa.Column("description", sa.Text, nullable=False),
            sa.Column("tech_stack", postgresql.JSON, nullable=False, server_default="[]"),
            sa.Column("published", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_real_projects_division", "real_projects", ["division"])
        op.create_index("ix_real_projects_slug", "real_projects", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_real_projects_slug", table_name="real_projects")
    op.drop_index("ix_real_projects_division", table_name="real_projects")
    op.drop_table("real_projects")
    op.drop_index("ix_career_paths_slug", table_name="career_paths")
    op.drop_index("ix_career_paths_division", table_name="career_paths")
    op.drop_table("career_paths")
