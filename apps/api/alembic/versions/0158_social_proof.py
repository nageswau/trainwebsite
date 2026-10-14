"""PUB-022 -- homepage social proof: testimonial publication/consent/featured/photo columns and the site rating badge.

Revision ID: 0158_social_proof
Revises: 0157_direct_tieups

docs/superpowers/specs/2026-10-14-pub-022-social-proof-design.md §3 (DEC-SCOPE-210). Every existing testimonial becomes
unpublished (SP4: the seeded demo rows must not stay public). 0001 builds a fresh database from the current models, so every
step is guarded. TESTIMONIAL_CHECKS / BADGE_CHECKS repeat app.models (test_pub_022_migration).
"""

import sqlalchemy as sa

from alembic import op

revision = "0158_social_proof"
down_revision = "0157_direct_tieups"
branch_labels = None
depends_on = None

TESTIMONIAL_CHECKS = {
    "ck_testimonials_publish_needs_consent": "NOT published OR consent_confirmed",
    "ck_testimonials_rating_range": "rating BETWEEN 1 AND 5",
    "ck_testimonials_division": "division IN ('it', 'overseas')",
}  # must equal app.models.TESTIMONIAL_CHECKS
BADGE_CHECKS = {
    "ck_site_rating_badge_single": "id = 1",
    "ck_site_rating_badge_rating": "rating >= 0 AND rating <= 5",
    "ck_site_rating_badge_count": "review_count >= 0",
}  # must equal app.models.RATING_BADGE_CHECKS
INDEX = "ix_testimonials_strip"


def _columns():
    return (
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("context", sa.String(160), nullable=True),
        sa.Column("consent_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consent_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("photo_key", sa.String(300), nullable=True),
        sa.Column("photo_content_type", sa.String(40), nullable=True),
    )


COLUMNS = tuple(c.name for c in _columns())


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    present = set() if inspector is None else {c["name"] for c in inspector.get_columns("testimonials")}
    for column in _columns():
        if column.name not in present:
            op.add_column("testimonials", column)
    # SP4: nothing published before consent existed stays public.
    op.execute("UPDATE testimonials SET published = false")
    if inspector is not None:
        bad = op.get_bind().execute(sa.text("SELECT id, division FROM testimonials WHERE division NOT IN ('it', 'overseas') LIMIT 1")).first()
        if bad:
            raise RuntimeError(f"Cannot upgrade to 0158_social_proof: testimonial {bad[0]} has division {bad[1]!r}; fix it to 'it' or 'overseas' first.")
    checks = set() if inspector is None else {c["name"] for c in inspector.get_check_constraints("testimonials")}
    for name, sql in TESTIMONIAL_CHECKS.items():
        if name not in checks:
            op.create_check_constraint(name, "testimonials", sql)
    indexes = set() if inspector is None else {i["name"] for i in inspector.get_indexes("testimonials")}
    if INDEX not in indexes:
        op.create_index(INDEX, "testimonials", ["division", "published", "featured", "display_order"])
    if inspector is None or not inspector.has_table("site_rating_badge"):
        op.create_table(
            "site_rating_badge",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
            sa.Column("source_name", sa.String(60), nullable=False),
            sa.Column("rating", sa.Numeric(2, 1), nullable=False),
            sa.Column("review_count", sa.Integer(), nullable=False),
            sa.Column("review_url", sa.String(500), nullable=True),
            sa.Column("as_of", sa.Date(), nullable=False),
            sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("updated_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in BADGE_CHECKS.items()),
        )


def downgrade() -> None:
    op.drop_table("site_rating_badge")
    op.drop_index(INDEX, table_name="testimonials")
    for name in reversed(TESTIMONIAL_CHECKS):
        op.drop_constraint(name, "testimonials", type_="check")
    for name in reversed(COLUMNS):
        op.drop_column("testimonials", name)
