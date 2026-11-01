from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import json
import re
import sqlite3
from typing import Any, Mapping

from evidencemill.models import EvidenceObservation


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type_name: str | None = None
    nullable: bool = True
    primary_key: bool = False


@dataclass(frozen=True)
class TableInfo:
    name: str
    columns: tuple[ColumnInfo, ...]

    @property
    def column_names(self) -> frozenset[str]:
        return frozenset(column.name for column in self.columns)


@dataclass(frozen=True)
class SchemaSnapshot:
    tables: dict[str, TableInfo]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SchemaSnapshot":
        tables: dict[str, TableInfo] = {}
        raw_tables = payload.get("tables", payload)
        for table_name, raw_columns in dict(raw_tables).items():
            columns = []
            for item in raw_columns:
                if isinstance(item, str):
                    columns.append(ColumnInfo(name=item))
                else:
                    columns.append(ColumnInfo(
                        name=str(item["name"]),
                        type_name=item.get("type_name"),
                        nullable=bool(item.get("nullable", True)),
                        primary_key=bool(item.get("primary_key", False)),
                    ))
            tables[str(table_name)] = TableInfo(
                name=str(table_name),
                columns=tuple(columns),
            )
        return cls(tables=tables)


@dataclass(frozen=True)
class SqlMapping:
    """Map neutral EvidenceMill fields into one SQL table.

    The columns mapping is target SQL column name -> EvidenceObservation path.
    Example paths: value, unit, source.source_id, context.row_header.
    """

    table: str
    columns: dict[str, str]
    constants: dict[str, Any] = field(default_factory=dict)
    omit_none: bool = True

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SqlMapping":
        return cls(
            table=str(payload["table"]),
            columns={str(k): str(v) for k, v in dict(payload.get("columns", {})).items()},
            constants=dict(payload.get("constants", {})),
            omit_none=bool(payload.get("omit_none", True)),
        )

    @classmethod
    def from_json(cls, text: str) -> "SqlMapping":
        return cls.from_dict(json.loads(text))

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "columns": dict(self.columns),
            "constants": dict(self.constants),
            "omit_none": self.omit_none,
        }


@dataclass(frozen=True)
class SqlDialect:
    paramstyle: str = "qmark"
    identifier_quote: str = '"'


SQLITE_DIALECT = SqlDialect(paramstyle="qmark", identifier_quote='"')
POSTGRES_DIALECT = SqlDialect(paramstyle="format", identifier_quote='"')
MYSQL_DIALECT = SqlDialect(paramstyle="format", identifier_quote=chr(96))


def resolve_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if is_dataclass(current):
            current = getattr(current, part)
        elif isinstance(current, Mapping):
            current = current.get(part)
        else:
            current = getattr(current, part)
    return current


def observation_row(observation: EvidenceObservation, mapping: SqlMapping) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for column, path in mapping.columns.items():
        value = resolve_path(observation, path)
        if mapping.omit_none and value is None:
            continue
        if isinstance(value, tuple):
            value = json.dumps(list(value), separators=(",", ":"))
        elif isinstance(value, (dict, list)):
            value = json.dumps(value, separators=(",", ":"), sort_keys=True)
        row[column] = value
    for column, value in mapping.constants.items():
        if not (mapping.omit_none and value is None):
            row[column] = value
    return row


def validate_mapping(mapping: SqlMapping, schema: SchemaSnapshot) -> list[str]:
    table = schema.tables.get(mapping.table)
    if table is None:
        return [f"table not found: {mapping.table}"]
    allowed = table.column_names
    unknown = sorted((set(mapping.columns) | set(mapping.constants)) - allowed)
    return [f"column not found in {mapping.table}: {column}" for column in unknown]


def sqlite_schema(connection: sqlite3.Connection) -> SchemaSnapshot:
    tables: dict[str, TableInfo] = {}
    names = [
        row[0]
        for row in connection.execute(
            """SELECT name
               FROM sqlite_master
               WHERE type='table' AND name NOT LIKE 'sqlite_%'
               ORDER BY name"""
        )
    ]
    for name in names:
        escaped = name.replace('"', '""')
        columns = []
        for row in connection.execute(f'PRAGMA table_info("{escaped}")'):
            columns.append(ColumnInfo(
                name=str(row[1]),
                type_name=str(row[2]) or None,
                nullable=not bool(row[3]),
                primary_key=bool(row[5]),
            ))
        tables[name] = TableInfo(name=name, columns=tuple(columns))
    return SchemaSnapshot(tables=tables)


def _quote(identifier: str, dialect: SqlDialect) -> str:
    if not identifier:
        raise ValueError("empty SQL identifier")
    quote = dialect.identifier_quote
    return quote + identifier.replace(quote, quote + quote) + quote


def _placeholders(columns: list[str], dialect: SqlDialect) -> tuple[list[str], str | None]:
    style = dialect.paramstyle
    if style == "qmark":
        return ["?"] * len(columns), None
    if style == "format":
        return ["%s"] * len(columns), None
    if style == "numeric":
        return [f":{i}" for i in range(1, len(columns) + 1)], None
    if style == "named":
        return [f":{column}" for column in columns], "mapping"
    if style == "pyformat":
        return [f"%({column})s" for column in columns], "mapping"
    raise ValueError(f"unsupported DB-API paramstyle: {style}")


def build_insert(
    mapping: SqlMapping,
    observation: EvidenceObservation,
    *,
    dialect: SqlDialect = SQLITE_DIALECT,
) -> tuple[str, tuple[Any, ...] | dict[str, Any]]:
    row = observation_row(observation, mapping)
    if not row:
        raise ValueError("mapping produced no SQL values")
    columns = list(row)
    placeholders, parameter_mode = _placeholders(columns, dialect)
    sql = (
        f"INSERT INTO {_quote(mapping.table, dialect)} "
        f"({', '.join(_quote(column, dialect) for column in columns)}) "
        f"VALUES ({', '.join(placeholders)})"
    )
    if parameter_mode == "mapping":
        return sql, {column: row[column] for column in columns}
    return sql, tuple(row[column] for column in columns)


def insert_dbapi(
    connection: Any,
    observation: EvidenceObservation,
    mapping: SqlMapping,
    *,
    dialect: SqlDialect,
    schema: SchemaSnapshot | None = None,
) -> int:
    if schema is not None:
        errors = validate_mapping(mapping, schema)
        if errors:
            raise ValueError("; ".join(errors))
    sql, params = build_insert(mapping, observation, dialect=dialect)
    cursor = connection.cursor()
    try:
        cursor.execute(sql, params)
        return cursor.rowcount
    finally:
        cursor.close()


def insert_sqlite(
    connection: sqlite3.Connection,
    observation: EvidenceObservation,
    mapping: SqlMapping,
) -> int:
    errors = validate_mapping(mapping, sqlite_schema(connection))
    if errors:
        raise ValueError("; ".join(errors))
    sql, params = build_insert(mapping, observation, dialect=SQLITE_DIALECT)
    cursor = connection.execute(sql, params)
    return cursor.rowcount


_PATH_HINTS = {
    "kind": "kind",
    "type": "kind",
    "value": "value",
    "unit": "unit",
    "source_id": "source.source_id",
    "source": "source.source_id",
    "source_location": "source.location",
    "location": "source.location",
    "raw_text": "source.raw_text",
    "text": "source.raw_text",
    "subject_hint": "subject_hint",
    "subject": "subject_hint",
    "property_hint": "property_hint",
    "property": "property_hint",
    "qualifiers": "qualifiers",
    "context": "context",
    "ambiguous": "ambiguous",
}


def suggest_mapping(schema: SchemaSnapshot, table: str) -> SqlMapping:
    """Build a conservative starter mapping from obvious column names."""
    info = schema.tables.get(table)
    if info is None:
        raise ValueError(f"table not found: {table}")
    columns: dict[str, str] = {}
    for column in info.columns:
        key = re.sub(r"[^a-z0-9]+", "_", column.name.casefold()).strip("_")
        path = _PATH_HINTS.get(key)
        if path:
            columns[column.name] = path
    return SqlMapping(table=table, columns=columns)


def mapping_template(schema: SchemaSnapshot, table: str) -> dict[str, Any]:
    mapping = suggest_mapping(schema, table)
    info = schema.tables[table]
    return {
        "mapping": mapping.to_dict(),
        "unmapped_columns": [
            column.name for column in info.columns if column.name not in mapping.columns
        ],
        "columns": [asdict(column) for column in info.columns],
    }


def sqlite_mapping_template(connection: sqlite3.Connection, table: str) -> dict[str, Any]:
    return mapping_template(sqlite_schema(connection), table)
