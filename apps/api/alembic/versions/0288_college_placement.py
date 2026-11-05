"""pob-013 -- a college's placement profile beside the BDM organization (DEC-SCOPE-410 P5-P10).

Revision ID: 0288_college_placement
Revises: 0285_job_revisions

docs/superpowers/specs/2026-11-05-pob-013-college-placement-profile-design.md. Additive only: five new tables and two nullable columns
on `bdm_organization_contacts`; no existing row changes. 0001 runs `create_all` from today's models, so a fresh database already has
everything: each step runs only when missing. CHECKS and CONTACT_METHOD_CHECK are frozen copies of `models.PLACEMENT_CHECKS` and
`models.PLACEMENT_CONTACT_METHOD_CHECK`. The downgrade drops what the upgrade added.
"""

import sqlalchemy as sa

from alembic import op

revision = "0288_college_placement"
down_revision = "0285_job_revisions"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_bdm_org_placement_batches_year": "pass_out_year BETWEEN 2000 AND 2100",
    "ck_bdm_org_placement_batches_students": "student_count IS NULL OR student_count BETWEEN 0 AND 100000",
    "ck_bdm_org_placement_events_kind": "kind IN ('pre_placement_talk', 'campus_drive', 'assessment', 'interview', 'exam', 'holiday', 'other')",
    "ck_bdm_org_placement_events_window": "ends_on IS NULL OR ends_on >= starts_on",
    "ck_bdm_org_tpo_interactions_channel": "channel IN ('meeting', 'call', 'email', 'whatsapp', 'visit', 'other')",
}
CONTACT_METHOD_CHECK = "preferred_contact_method IS NULL OR preferred_contact_method IN ('email', 'phone', 'whatsapp', 'in_person', 'linkedin')"
CONTACTS = "bdm_organization_contacts"
TABLES = ("bdm_org_tpo_interactions", "bdm_org_placement_events", "bdm_org_placement_batches", "bdm_org_courses", "bdm_org_placement_profiles")


def _org() -> sa.Column:
    return sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), nullable=False)


def _user(name: str) -> sa.Column:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


def _stamps() -> list[sa.Column]:
    return [sa.Column(n, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False) for n in ("created_at", "updated_at")]


def _check(name: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(CHECKS[name], name=name)


def _existing() -> tuple[set, set, set]:
    if op.get_context().as_sql:
        return set(), set(), set()
    inspector = sa.inspect(op.get_bind())
    return (
        set(inspector.get_table_names()),
        {c["name"] for c in inspector.get_columns(CONTACTS)},
        {c["name"] for c in inspector.get_check_constraints(CONTACTS)},
    )


def upgrade() -> None:
    tables, columns, checks = _existing()
    if "office_details" not in columns:
        op.add_column(CONTACTS, sa.Column("office_details", sa.String(300), nullable=True))
    if "preferred_contact_method" not in columns:
        op.add_column(CONTACTS, sa.Column("preferred_contact_method", sa.String(20), nullable=True))
    if "ck_bdm_organization_contacts_preferred_method" not in checks:
        op.create_check_constraint("ck_bdm_organization_contacts_preferred_method", CONTACTS, CONTACT_METHOD_CHECK)
    if "bdm_org_placement_profiles" not in tables:
        op.create_table(
            "bdm_org_placement_profiles",
            sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT"), primary_key=True),
            sa.Column("drive_process", sa.Text(), nullable=True),
            sa.Column("eligibility_rules", sa.Text(), nullable=True),
            _user("updated_by_user_id"),
            *_stamps(),
        )
    if "bdm_org_courses" not in tables:
        op.create_table(
            "bdm_org_courses",
            sa.Column("id", sa.Uuid(), primary_key=True),
            _org(),
            sa.Column("department", sa.String(120), nullable=True),
            sa.Column("course", sa.String(120), nullable=False),
            sa.Column("course_key", sa.String(250), nullable=False),
            *_stamps(),
            sa.UniqueConstraint("organization_id", "course_key", name="uq_bdm_org_courses_key"),
        )
    if "bdm_org_placement_batches" not in tables:
        op.create_table(
            "bdm_org_placement_batches",
            sa.Column("id", sa.Uuid(), primary_key=True),
            _org(),
            sa.Column("course_id", sa.Uuid(), sa.ForeignKey("bdm_org_courses.id", ondelete="RESTRICT"), nullable=True),
            sa.Column("pass_out_year", sa.SmallInteger(), nullable=False),
            sa.Column("pass_out_date", sa.Date(), nullable=True),
            sa.Column("student_count", sa.Integer(), nullable=True),
            sa.Column("notes", sa.String(500), nullable=True),
            _user("created_by_user_id"),
            *_stamps(),
            _check("ck_bdm_org_placement_batches_year"),
            _check("ck_bdm_org_placement_batches_students"),
        )
        op.create_index("ix_bdm_org_placement_batches_org_year", "bdm_org_placement_batches", ["organization_id", "pass_out_year"])
        op.create_index("ix_bdm_org_placement_batches_course", "bdm_org_placement_batches", ["course_id"])
    if "bdm_org_placement_events" not in tables:
        op.create_table(
            "bdm_org_placement_events",
            sa.Column("id", sa.Uuid(), primary_key=True),
            _org(),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False),
            sa.Column("starts_on", sa.Date(), nullable=False),
            sa.Column("ends_on", sa.Date(), nullable=True),
            sa.Column("notes", sa.String(500), nullable=True),
            _user("created_by_user_id"),
            *_stamps(),
            _check("ck_bdm_org_placement_events_kind"),
            _check("ck_bdm_org_placement_events_window"),
        )
        op.create_index("ix_bdm_org_placement_events_org_start", "bdm_org_placement_events", ["organization_id", "starts_on"])
    if "bdm_org_tpo_interactions" not in tables:
        op.create_table(
            "bdm_org_tpo_interactions",
            sa.Column("id", sa.Uuid(), primary_key=True),
            _org(),
            sa.Column("contact_id", sa.Uuid(), sa.ForeignKey("bdm_organization_contacts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("contact_name", sa.String(200), nullable=True),
            sa.Column("channel", sa.String(20), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("next_step", sa.String(500), nullable=True),
            _user("logged_by_user_id"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            _check("ck_bdm_org_tpo_interactions_channel"),
        )
        op.create_index("ix_bdm_org_tpo_interactions_org_occurred", "bdm_org_tpo_interactions", ["organization_id", "occurred_at"])


def downgrade() -> None:
    for table in TABLES:
        op.drop_table(table)
    op.drop_constraint("ck_bdm_organization_contacts_preferred_method", CONTACTS, type_="check")
    op.drop_column(CONTACTS, "preferred_contact_method")
    op.drop_column(CONTACTS, "office_details")
