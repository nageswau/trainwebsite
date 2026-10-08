"""upc-006 -- University contacts + relationship strength.

Revision ID: 0107_university_contacts
Revises: 0106_rec_companies

docs/superpowers/specs/2026-10-08-upc-006-university-contacts-design.md §2 (DEC-SCOPE-122). Adds `universities.relationship_strength`, the
seeded `university_contact_roles` catalogue and `university_contacts`. 0001 builds a fresh database from the current models, which
already carry all of this (with an empty catalogue), so each step is guarded and the seed is ON CONFLICT DO NOTHING. UNIVERSITY_CHECK,
CONTACT_CHECKS and ROLE_SEED repeat app.models (test_upc_006_migration). downgrade() refuses while any contact or any relationship
strength exists: it would drop contact PII and recorded assessments.

Re-chained 2026-10-08 on merging `main` @ `035c99ad`: drafted as `0106_university_contacts` on `0105_university_master`, but rec-003's
`0106_rec_companies` merged first, so this is `0107` after it (DEC-SCOPE-122, API §12AP, RBAC §2.48). A database stamped at
`0106_university_contacts` is re-stamped with `alembic stamp --purge 0105_university_master`, then `upgrade head` (every step here is guarded).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0107_university_contacts"
down_revision = "0106_rec_companies"
branch_labels = None
depends_on = None

STRENGTHS = "'new', 'developing', 'good', 'strong', 'strategic', 'at_risk', 'dormant'"
UNIVERSITY_CHECK = f"relationship_strength IS NULL OR relationship_strength IN ({STRENGTHS})"
UNIVERSITY_CHECK_NAME = "ck_universities_relationship_strength"
CONTACT_CHECKS = {
    "ck_university_contacts_preferred_channel": "preferred_channel IS NULL OR preferred_channel IN ('email', 'phone', 'whatsapp', 'linkedin')",
    "ck_university_contacts_relationship_strength": UNIVERSITY_CHECK,
}
ROLE_SEED = (
    ("international_director", "International Director"),
    ("international_recruitment_manager", "International Recruitment Manager"),
    ("regional_manager", "Regional Manager"),
    ("admissions_manager", "Admissions Manager"),
    ("marketing_manager", "Marketing Manager"),
    ("application_officer", "Application Officer"),
    ("finance_contact", "Finance Contact"),
    ("international_office", "International Office"),
    ("partnership_contact", "Partnership Contact"),
    ("recruitment_contact", "Recruitment Contact"),
    ("application_contact", "Application Contact"),
    ("country_manager", "Country Manager"),
)
UUID = postgresql.UUID(as_uuid=True)


def _inspector():
    return None if op.get_context().as_sql else sa.inspect(op.get_bind())  # offline SQL: emit everything


def upgrade() -> None:
    inspector = _inspector()
    if inspector is None or "relationship_strength" not in {c["name"] for c in inspector.get_columns("universities")}:
        op.add_column("universities", sa.Column("relationship_strength", sa.String(12), nullable=True))
    if inspector is None or UNIVERSITY_CHECK_NAME not in {c["name"] for c in inspector.get_check_constraints("universities")}:
        op.create_check_constraint(UNIVERSITY_CHECK_NAME, "universities", UNIVERSITY_CHECK)

    tables = set() if inspector is None else set(inspector.get_table_names())
    if "university_contact_roles" not in tables:
        op.create_table(
            "university_contact_roles",
            sa.Column("code", sa.String(40), primary_key=True),
            sa.Column("label", sa.String(80), nullable=False),
            sa.Column("position", sa.SmallInteger(), nullable=False),
        )
    for position, (code, label) in enumerate(ROLE_SEED, start=1):
        op.execute(
            sa.text("INSERT INTO university_contact_roles (code, label, position) VALUES (:code, :label, :position) ON CONFLICT (code) DO NOTHING").bindparams(
                code=code, label=label, position=position
            )
        )
    if "university_contacts" not in tables:
        op.create_table(
            "university_contacts",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("university_id", UUID, sa.ForeignKey("universities.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("designation", sa.String(120), nullable=True),
            sa.Column("department", sa.String(120), nullable=True),
            sa.Column("role_code", sa.String(40), sa.ForeignKey("university_contact_roles.code", ondelete="RESTRICT"), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("phone", sa.String(30), nullable=True),
            sa.Column("whatsapp", sa.String(30), nullable=True),
            sa.Column("linkedin", sa.String(300), nullable=True),
            sa.Column("preferred_channel", sa.String(10), nullable=True),
            sa.Column("relationship_strength", sa.String(12), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("shareable", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            *(sa.CheckConstraint(sql, name=name) for name, sql in CONTACT_CHECKS.items()),
        )
        op.create_index("ix_university_contacts_university", "university_contacts", ["university_id"])
        op.create_index("uq_university_contacts_primary", "university_contacts", ["university_id"], unique=True, postgresql_where=sa.text("is_primary"))
        op.create_index("uq_university_contacts_email", "university_contacts", ["university_id", sa.text("lower(email)")], unique=True, postgresql_where=sa.text("email IS NOT NULL"))


def downgrade() -> None:
    if not op.get_context().as_sql:
        found = op.get_bind().execute(sa.text("SELECT 1 FROM university_contacts UNION ALL SELECT 1 FROM universities WHERE relationship_strength IS NOT NULL LIMIT 1")).first()
        if found:
            raise RuntimeError("Cannot downgrade 0107_university_contacts: contacts or relationship strengths exist. Remove them deliberately first.")
    op.drop_table("university_contacts")
    op.drop_table("university_contact_roles")
    op.drop_constraint(UNIVERSITY_CHECK_NAME, "universities", type_="check")
    op.drop_column("universities", "relationship_strength")
