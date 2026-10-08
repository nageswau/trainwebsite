"""rec-006 -- the recruiter Skills Master: skill_categories, skills, skill_category_tags, skill_aliases, skill_related (seeded).

Revision ID: 0103_skills_master
Revises: 0102_rec_catalogues

docs/superpowers/specs/2026-10-08-rec-006-skills-master-design.md §2 (DEC-SCOPE-118). Adds five tables; no existing row is read or
written. 0001 builds a fresh database from the current models, which already carry these tables, so creation is guarded (0076's idiom)
-- but the seed always runs, and inserts only what is missing (by lower(name) / lower(alias)), so it is idempotent and never
overwrites a manager's edit. downgrade() refuses while manager data exists (anything that differs from the seed).
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0103_skills_master"
down_revision = "0102_rec_catalogues"
branch_labels = None
depends_on = None

# EVID-018 S2-§2 (lines 1126-1216), in source order. JavaScript is listed under Programming and again under Frontend: one skill with
# Programming as its primary category and a Frontend tag (backlog AC1).
CATEGORIES = {
    "Programming": ("Java", "Python", "JavaScript", "C", "C++", "C#", "PHP"),
    "Java Technologies": ("Core Java", "Advanced Java", "Spring", "Spring Boot", "Hibernate", "JPA", "Microservices", "REST API", "Maven", "Gradle", "JSP", "Servlets"),
    "Frontend": ("HTML", "CSS", "React", "Angular", "Vue.js"),
    "Database": ("SQL", "MySQL", "PostgreSQL", "Oracle", "MongoDB", "SQL Server"),
    "Cloud/DevOps": ("AWS", "Azure", "GCP", "Docker", "Kubernetes", "Jenkins", "Git"),
}
TAGS = (("JavaScript", "Frontend"),)
# S2-§16 (lines 1607-1643). "Core Java" is also a §2 skill and an alias may not equal a skill name, so it is a related pair (S4).
ALIASES = {"Java": ("Java 8", "Java 11", "Java 17", "Java 21", "J2EE", "J2SE"), "React": ("React.js", "ReactJS", "React JS")}
RELATED = (("Java", "Core Java"),)

_SKILL_ID = "(SELECT id FROM skills WHERE lower(name) = lower(CAST(:{} AS varchar)))"
_CATEGORY_ID = "(SELECT id FROM skill_categories WHERE lower(name) = lower(CAST(:{} AS varchar)))"


def seed_statements() -> list[tuple[str, dict]]:
    """One INSERT per seed row, each skipped when its row (or, for an alias, the term) already exists. Explicit casts: a parameter used
    twice must have one type for asyncpg."""
    out = []
    for c_order, (category, skills) in enumerate(CATEGORIES.items(), start=1):
        out.append((
            "INSERT INTO skill_categories (id, name, sort_order) SELECT CAST(:id AS uuid), CAST(:name AS varchar), CAST(:sort AS integer) "
            "WHERE NOT EXISTS (SELECT 1 FROM skill_categories WHERE lower(name) = lower(CAST(:name AS varchar)))",
            {"id": uuid.uuid4(), "name": category, "sort": c_order},
        ))
        for s_order, skill in enumerate(skills, start=1):
            out.append((
                f"INSERT INTO skills (id, name, category_id, sort_order) SELECT CAST(:id AS uuid), CAST(:name AS varchar), {_CATEGORY_ID.format('category')}, "
                "CAST(:sort AS integer) WHERE NOT EXISTS (SELECT 1 FROM skills WHERE lower(name) = lower(CAST(:name AS varchar)))",
                {"id": uuid.uuid4(), "name": skill, "category": category, "sort": s_order},
            ))
    for skill, category in TAGS:
        out.append((
            f"INSERT INTO skill_category_tags (skill_id, category_id) SELECT {_SKILL_ID.format('skill')}, {_CATEGORY_ID.format('category')} "
            "WHERE NOT EXISTS (SELECT 1 FROM skill_category_tags t JOIN skills s ON s.id = t.skill_id JOIN skill_categories c ON c.id = t.category_id "
            "WHERE lower(s.name) = lower(CAST(:skill AS varchar)) AND lower(c.name) = lower(CAST(:category AS varchar)))",
            {"skill": skill, "category": category},
        ))
    for skill, aliases in ALIASES.items():
        for alias in aliases:
            out.append((
                f"INSERT INTO skill_aliases (id, skill_id, alias) SELECT CAST(:id AS uuid), {_SKILL_ID.format('skill')}, CAST(:alias AS varchar) "
                "WHERE NOT EXISTS (SELECT 1 FROM skill_aliases WHERE lower(alias) = lower(CAST(:alias AS varchar))) "
                "AND NOT EXISTS (SELECT 1 FROM skills WHERE lower(name) = lower(CAST(:alias AS varchar)))",
                {"id": uuid.uuid4(), "skill": skill, "alias": alias},
            ))
    for a, b in RELATED:
        out.append((
            f"INSERT INTO skill_related (skill_a_id, skill_b_id) SELECT LEAST(x, y), GREATEST(x, y) FROM (SELECT {_SKILL_ID.format('a')} AS x, "
            f"{_SKILL_ID.format('b')} AS y) p WHERE x IS NOT NULL AND y IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM skill_related WHERE skill_a_id = LEAST(x, y) AND skill_b_id = GREATEST(x, y))",
            {"a": a, "b": b},
        ))
    return out


def upgrade() -> None:
    bind = op.get_bind()
    if op.get_context().as_sql or "skills" not in sa.inspect(bind).get_table_names():
        uuid_col = postgresql.UUID(as_uuid=True)
        def stamps():
            return (
                sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
                sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            )

        op.create_table(
            "skill_categories",
            sa.Column("id", uuid_col, primary_key=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
            *stamps(),
        )
        op.create_index("uq_skill_categories_name", "skill_categories", [sa.text("lower(name)")], unique=True)
        op.create_table(
            "skills",
            sa.Column("id", uuid_col, primary_key=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("category_id", uuid_col, sa.ForeignKey("skill_categories.id"), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
            *stamps(),
        )
        op.create_index("uq_skills_name", "skills", [sa.text("lower(name)")], unique=True)
        op.create_index("ix_skills_category", "skills", ["category_id"])
        op.create_table(
            "skill_category_tags",
            sa.Column("skill_id", uuid_col, sa.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("category_id", uuid_col, sa.ForeignKey("skill_categories.id"), primary_key=True),
        )
        op.create_table(
            "skill_aliases",
            sa.Column("id", uuid_col, primary_key=True),
            sa.Column("skill_id", uuid_col, sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
            sa.Column("alias", sa.String(80), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("uq_skill_aliases_alias", "skill_aliases", [sa.text("lower(alias)")], unique=True)
        op.create_index("ix_skill_aliases_skill", "skill_aliases", ["skill_id"])
        op.create_table(
            "skill_related",
            sa.Column("skill_a_id", uuid_col, sa.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("skill_b_id", uuid_col, sa.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
            sa.CheckConstraint("skill_a_id < skill_b_id", name="ck_skill_related_order"),
        )
    for statement, params in seed_statements():
        op.execute(sa.text(statement).bindparams(**params))


def _matches_seed(bind) -> bool:
    rows = lambda sql: {tuple(r) for r in bind.execute(sa.text(sql)).all()}  # noqa: E731
    categories = {(name, True, order) for order, name in enumerate(CATEGORIES, start=1)}
    skills = {(s, c, True, o) for c, names in CATEGORIES.items() for o, s in enumerate(names, start=1)}
    return (
        rows("SELECT name, active, sort_order FROM skill_categories") == categories
        and rows("SELECT s.name, c.name, s.active, s.sort_order FROM skills s JOIN skill_categories c ON c.id = s.category_id") == skills
        and rows("SELECT s.name, c.name FROM skill_category_tags t JOIN skills s ON s.id = t.skill_id JOIN skill_categories c ON c.id = t.category_id") == set(TAGS)
        and rows("SELECT s.name, a.alias FROM skill_aliases a JOIN skills s ON s.id = a.skill_id") == {(s, a) for s, aliases in ALIASES.items() for a in aliases}
        and rows("SELECT LEAST(a.name, b.name), GREATEST(a.name, b.name) FROM skill_related r JOIN skills a ON a.id = r.skill_a_id "
                 "JOIN skills b ON b.id = r.skill_b_id") == {(min(a, b), max(a, b)) for a, b in RELATED}
    )


def downgrade() -> None:
    if not op.get_context().as_sql and not _matches_seed(op.get_bind()):
        raise RuntimeError("Cannot downgrade 0103_skills_master: manager data exists (skills, categories or aliases differ from the seed). Remove it deliberately first.")
    for table in ("skill_related", "skill_aliases", "skill_category_tags", "skills", "skill_categories"):
        op.drop_table(table)
