"""Replace generated integer identifiers with UUID identifiers.

Revision ID: 0004_uuid_identifiers
Revises: 0003_operational_workflows

The migration keeps every existing row, creates a UUID for each record, maps
all relationships to those UUIDs, and then rebuilds the affected constraints.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.models import Base


revision = "0004_uuid_identifiers"
down_revision = "0003_operational_workflows"
branch_labels = None
depends_on = None


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _is_uuid(column_type: object) -> bool:
    return isinstance(column_type, (sa.Uuid, postgresql.UUID)) or str(column_type).upper() == "UUID"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("The UUID data-preserving migration requires PostgreSQL")

    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    tables = [name for name in Base.metadata.tables if name in existing_tables]
    if not tables:
        return

    user_identifier = next(column for column in inspector.get_columns("users") if column["name"] == "id")
    if _is_uuid(user_identifier["type"]):
        # Fresh installations are created from the current UUID metadata by
        # the baseline migration, so no conversion is necessary.
        return

    primary_keys: dict[str, dict] = {}
    foreign_keys: list[dict] = []
    unique_constraints: list[dict] = []
    indexes: list[dict] = []
    nullable: dict[tuple[str, str], bool] = {}

    for table in tables:
        primary_keys[table] = inspector.get_pk_constraint(table)
        table_foreign_keys = inspector.get_foreign_keys(table)
        for item in table_foreign_keys:
            foreign_keys.append({"table": table, **item})
        changed = {"id", *(column for item in table_foreign_keys for column in item["constrained_columns"])}
        for column in inspector.get_columns(table):
            if column["name"] in changed:
                nullable[(table, column["name"])] = bool(column["nullable"])
        for item in inspector.get_unique_constraints(table):
            if changed.intersection(item.get("column_names") or []):
                unique_constraints.append({"table": table, **item})
        for item in inspector.get_indexes(table):
            if changed.intersection(item.get("column_names") or []) and not item.get("duplicates_constraint"):
                indexes.append({"table": table, **item})

    uuid_type = postgresql.UUID(as_uuid=True)
    for table in tables:
        op.add_column(
            table,
            sa.Column("__uuid_id", uuid_type, nullable=True, server_default=sa.text("gen_random_uuid()")),
        )
        bind.execute(sa.text(f"UPDATE {_quoted(table)} SET __uuid_id = gen_random_uuid() WHERE __uuid_id IS NULL"))

    # University representatives have a scoped university reference in JSON.
    # Translate it before the old university identifier is removed.
    if {"users", "universities"}.issubset(existing_tables):
        bind.execute(sa.text(
            "UPDATE users AS account SET profile = "
            "jsonb_set(COALESCE(account.profile::jsonb, '{}'::jsonb), '{university_id}', "
            "to_jsonb(university.__uuid_id::text))::json "
            "FROM universities AS university "
            "WHERE account.profile->>'university_id' = university.id::text"
        ))

    for relation in foreign_keys:
        table = relation["table"]
        referred_table = relation["referred_table"]
        if referred_table not in tables:
            raise RuntimeError(f"Cannot migrate relationship from {table} to missing table {referred_table}")
        for column, referred_column in zip(relation["constrained_columns"], relation["referred_columns"]):
            if referred_column != "id":
                raise RuntimeError(f"Unsupported UUID relationship target: {referred_table}.{referred_column}")
            temporary = f"__uuid_{column}"
            op.add_column(table, sa.Column(temporary, uuid_type, nullable=True))
            bind.execute(sa.text(
                f"UPDATE {_quoted(table)} AS child SET {_quoted(temporary)} = parent.__uuid_id "
                f"FROM {_quoted(referred_table)} AS parent "
                f"WHERE child.{_quoted(column)} = parent.id"
            ))
            orphan_count = bind.execute(sa.text(
                f"SELECT count(*) FROM {_quoted(table)} "
                f"WHERE {_quoted(column)} IS NOT NULL AND {_quoted(temporary)} IS NULL"
            )).scalar_one()
            if orphan_count:
                raise RuntimeError(f"Found {orphan_count} orphaned values in {table}.{column}")

    for relation in foreign_keys:
        if relation.get("name"):
            op.drop_constraint(relation["name"], relation["table"], type_="foreignkey")
    for index in indexes:
        op.drop_index(index["name"], table_name=index["table"])
    for constraint in unique_constraints:
        if constraint.get("name"):
            op.drop_constraint(constraint["name"], constraint["table"], type_="unique")
    for table, key in primary_keys.items():
        if key.get("name"):
            op.drop_constraint(key["name"], table, type_="primary")

    for relation in foreign_keys:
        table = relation["table"]
        for column in relation["constrained_columns"]:
            op.drop_column(table, column)
            op.alter_column(table, f"__uuid_{column}", new_column_name=column)

    for table in tables:
        op.drop_column(table, "id")
        op.alter_column(table, "__uuid_id", new_column_name="id", nullable=False)

    for table, key in primary_keys.items():
        op.create_primary_key(key.get("name") or f"{table}_pkey", table, ["id"])

    for relation in foreign_keys:
        options = relation.get("options") or {}
        op.create_foreign_key(
            relation.get("name") or f"fk_{relation['table']}_{'_'.join(relation['constrained_columns'])}",
            relation["table"],
            relation["referred_table"],
            relation["constrained_columns"],
            relation["referred_columns"],
            onupdate=options.get("onupdate"),
            ondelete=options.get("ondelete"),
            deferrable=options.get("deferrable"),
            initially=options.get("initially"),
        )
        for column in relation["constrained_columns"]:
            op.alter_column(relation["table"], column, nullable=nullable[(relation["table"], column)])

    for constraint in unique_constraints:
        op.create_unique_constraint(
            constraint.get("name") or f"uq_{constraint['table']}_{'_'.join(constraint['column_names'])}",
            constraint["table"],
            constraint["column_names"],
        )
    for index in indexes:
        op.create_index(
            index["name"],
            index["table"],
            index["column_names"],
            unique=bool(index.get("unique")),
        )


def downgrade() -> None:
    raise RuntimeError("UUID identifiers cannot be safely converted back to generated integers")
