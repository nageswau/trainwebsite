"""hrc-017 -- the skills taxonomy: `skill_categories.domain` (IT / non-IT), `job_skills.min_level` and the non-IT category seed.

Revision ID: 0265_skill_taxonomy
Revises: 0264_candidate_notes_tasks

docs/superpowers/specs/2026-11-04-hrc-017-skills-taxonomy-design.md (DEC-SCOPE-388). 0001 builds a fresh database from the current
models, which already carry the columns, so each step runs only when missing (0262's idiom). The server default makes every existing
category `it` (T1). The seed (T2, Q-17: a provisional list, NEEDS_CONFIRMATION) is 0104's insert-if-missing: an existing category is
reused as it is, a skill whose name is already a skill or an alias is skipped, so it never overwrites a manager's edit (T3). The
constants are frozen copies of the models at this revision (test_hrc_017_migration). The downgrade deletes the seeded rows nothing
references, then drops both columns.
"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0265_skill_taxonomy"
down_revision = "0264_candidate_notes_tasks"
branch_labels = None
depends_on = None

DOMAINS = ("it", "non_it")
LEVELS = ("beginner", "intermediate", "advanced", "expert")
DOMAIN_CHECK = "domain IN ('it', 'non_it')"
MIN_LEVEL_CHECK = "min_level IS NULL OR min_level IN ('beginner', 'intermediate', 'advanced', 'expert')"

# PDF §7.3 categories other than IT; the skills are the builder's starter list (Q-17) -- the owner edits them in the Skills Master.
CATEGORIES = {
    "Engineering": ("AutoCAD", "SolidWorks", "CATIA", "MATLAB", "PLC Programming", "Quality Control", "Lean Six Sigma"),
    "Healthcare": ("Patient Care", "Nursing", "Medical Coding", "Medical Billing", "Phlebotomy", "Clinical Documentation", "First Aid and CPR"),
    "Pharmacy": ("Pharmacovigilance", "Clinical Research", "Regulatory Affairs", "Good Manufacturing Practice", "Medical Writing", "Drug Dispensing", "Clinical Data Management"),
    "Finance": ("Accounting", "Tally ERP", "GST", "Income Tax", "Financial Analysis", "Accounts Payable", "Accounts Receivable", "Auditing"),
    "Sales": ("B2B Sales", "Inside Sales", "Field Sales", "Lead Generation", "Negotiation", "Key Account Management", "Business Development"),
    "Human Resources": ("Recruitment", "Payroll", "Onboarding", "Employee Relations", "Performance Management", "HR Policies", "Labour Law Compliance"),
}
ALIASES = {"Good Manufacturing Practice": ("GMP",), "Tally ERP": ("Tally",), "First Aid and CPR": ("CPR",)}

_CATEGORY_ID = "(SELECT id FROM skill_categories WHERE lower(name) = lower(CAST(:category AS varchar)))"
_TERM_FREE = (
    "NOT EXISTS (SELECT 1 FROM skills WHERE lower(name) = lower(CAST(:{0} AS varchar))) "
    "AND NOT EXISTS (SELECT 1 FROM skill_aliases WHERE lower(alias) = lower(CAST(:{0} AS varchar)))"
)


def seed_statements() -> list[tuple[str, dict]]:
    """One INSERT per seed row, each skipped when its row (or its term) already exists. New categories sort after every existing one."""
    out = []
    for category, skills in CATEGORIES.items():
        out.append((
            "INSERT INTO skill_categories (id, name, domain, sort_order) SELECT CAST(:id AS uuid), CAST(:category AS varchar), 'non_it', "
            "COALESCE((SELECT max(sort_order) FROM skill_categories), 0) + 1 "
            "WHERE NOT EXISTS (SELECT 1 FROM skill_categories WHERE lower(name) = lower(CAST(:category AS varchar)))",
            {"id": uuid.uuid4(), "category": category},
        ))
        for s_order, skill in enumerate(skills, start=1):
            out.append((
                f"INSERT INTO skills (id, name, category_id, sort_order) SELECT CAST(:id AS uuid), CAST(:name AS varchar), {_CATEGORY_ID}, "
                f"CAST(:sort AS integer) WHERE {_TERM_FREE.format('name')}",
                {"id": uuid.uuid4(), "name": skill, "category": category, "sort": s_order},
            ))
    for skill, aliases in ALIASES.items():
        for alias in aliases:
            out.append((
                "INSERT INTO skill_aliases (id, skill_id, alias) SELECT CAST(:id AS uuid), s.id, CAST(:alias AS varchar) FROM skills s "
                f"WHERE lower(s.name) = lower(CAST(:skill AS varchar)) AND {_TERM_FREE.format('alias')}",
                {"id": uuid.uuid4(), "skill": skill, "alias": alias},
            ))
    return out


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    for table, column, ctype, default, check_name, check in (
        ("skill_categories", "domain", sa.String(10), sa.text("'it'"), "ck_skill_categories_domain", DOMAIN_CHECK),
        ("job_skills", "min_level", sa.String(16), None, "ck_job_skills_min_level", MIN_LEVEL_CHECK),
    ):
        if offline or column not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column(column, ctype, nullable=default is None, server_default=default))
        if offline or check_name not in {c["name"] for c in inspector.get_check_constraints(table)}:
            op.create_check_constraint(check_name, table, check)
    for statement, params in seed_statements():
        op.execute(sa.text(statement).bindparams(**params))


_UNREFERENCED = (
    "NOT EXISTS (SELECT 1 FROM job_skills j WHERE j.skill_id = skills.id) AND NOT EXISTS (SELECT 1 FROM candidate_skills c WHERE c.skill_id = skills.id) "
    "AND NOT EXISTS (SELECT 1 FROM program_skills p WHERE p.skill_id = skills.id)"
)


def downgrade() -> None:
    """Seeded rows go only while unused: a skill on a job, a candidate or a program stays (and so does its category)."""
    names = [s for skills in CATEGORIES.values() for s in skills]
    op.execute(sa.text(f"DELETE FROM skills WHERE lower(name) IN :names AND category_id IN (SELECT id FROM skill_categories WHERE domain = 'non_it') AND {_UNREFERENCED}").bindparams(
        sa.bindparam("names", [n.lower() for n in names], expanding=True)))
    op.execute(sa.text(
        "DELETE FROM skill_categories c WHERE c.domain = 'non_it' AND lower(c.name) IN :names "
        "AND NOT EXISTS (SELECT 1 FROM skills s WHERE s.category_id = c.id) AND NOT EXISTS (SELECT 1 FROM skill_category_tags t WHERE t.category_id = c.id)"
    ).bindparams(sa.bindparam("names", [n.lower() for n in CATEGORIES], expanding=True)))
    op.drop_constraint("ck_job_skills_min_level", "job_skills", type_="check")
    op.drop_column("job_skills", "min_level")
    op.drop_constraint("ck_skill_categories_domain", "skill_categories", type_="check")
    op.drop_column("skill_categories", "domain")
