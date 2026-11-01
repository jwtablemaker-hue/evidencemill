# SQL adapter

EvidenceMill can map neutral observations into an existing SQL table without
teaching the extraction core anything about that database's domain.

A mapping is ordinary JSON. The left side is the target SQL column. The right
side is a path on an EvidenceObservation.

Example:

    {
      "table": "observations",
      "columns": {
        "kind": "kind",
        "source_id": "source.source_id",
        "source_location": "source.location",
        "raw_text": "source.raw_text",
        "value": "value",
        "unit": "unit",
        "subject_hint": "subject_hint",
        "property_hint": "property_hint",
        "ambiguous": "ambiguous",
        "context_json": "context"
      },
      "constants": {
        "ingest_source": "evidencemill"
      }
    }

## SQLite

SQLite is supported out of the box. sqlite_mapping_template() inspects a live
table and returns a conservative starter mapping plus every unmapped column.

    import sqlite3
    from evidencemill.adapters.sql import SqlMapping, insert_sqlite, sqlite_mapping_template

    con = sqlite3.connect("target.sqlite")
    print(sqlite_mapping_template(con, "observations"))

    mapping = SqlMapping.from_dict({...})
    insert_sqlite(con, observation, mapping)
    con.commit()

## Other SQL engines

The mapping contract is database-neutral. build_insert() supports the standard
DB-API placeholder styles qmark, format, numeric, named, and pyformat. Built-in
dialect presets are included for SQLite, PostgreSQL-style, and MySQL-style SQL
generation.

Schema introspection is currently built in for SQLite. For another engine,
provide its table and column metadata as a SchemaSnapshot, then use the same
mapping and validation functions. Database-specific code stays at the edge
instead of leaking into EvidenceMill's extraction core.
