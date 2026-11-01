import sqlite3
import unittest

from evidencemill.adapters.sql import (
    POSTGRES_DIALECT,
    SchemaSnapshot,
    SqlMapping,
    build_insert,
    insert_sqlite,
    sqlite_mapping_template,
    sqlite_schema,
    suggest_mapping,
)
from evidencemill.models import EvidenceObservation, SourceRef


class SqlAdapterTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute(
            """CREATE TABLE observations(
                 id INTEGER PRIMARY KEY,
                 kind TEXT NOT NULL,
                 source_id TEXT,
                 location TEXT,
                 raw_text TEXT,
                 value TEXT,
                 unit TEXT,
                 subject_hint TEXT,
                 property_hint TEXT,
                 ambiguous INTEGER,
                 context TEXT
               )"""
        )
        self.obs = EvidenceObservation(
            kind="table_cell",
            source=SourceRef("manual-1", "table-2:r3c4", "500"),
            value="500",
            unit="W",
            subject_hint="Base",
            property_hint="Rated power",
            context={"row": 3, "column": 4},
            ambiguous=False,
        )

    def tearDown(self):
        self.con.close()

    def test_schema_introspection_and_template(self):
        schema = sqlite_schema(self.con)
        self.assertIn("observations", schema.tables)
        mapping = suggest_mapping(schema, "observations")
        self.assertEqual(mapping.columns["source_id"], "source.source_id")
        self.assertEqual(mapping.columns["property_hint"], "property_hint")

        template = sqlite_mapping_template(self.con, "observations")
        self.assertIn("id", template["unmapped_columns"])

    def test_portable_schema_and_parameter_style(self):
        schema = SchemaSnapshot.from_dict({
            "events": [
                {"name": "source_id", "type_name": "text"},
                {"name": "value", "type_name": "text"},
            ]
        })
        mapping = SqlMapping(
            table="events",
            columns={
                "source_id": "source.source_id",
                "value": "value",
            },
        )
        self.assertEqual(schema.tables["events"].column_names, {"source_id", "value"})
        sql, params = build_insert(mapping, self.obs, dialect=POSTGRES_DIALECT)
        self.assertEqual(
            sql,
            'INSERT INTO "events" ("source_id", "value") VALUES (%s, %s)',
        )
        self.assertEqual(params, ("manual-1", "500"))

    def test_mapping_validates_and_inserts(self):
        mapping = SqlMapping(
            table="observations",
            columns={
                "kind": "kind",
                "source_id": "source.source_id",
                "location": "source.location",
                "raw_text": "source.raw_text",
                "value": "value",
                "unit": "unit",
                "subject_hint": "subject_hint",
                "property_hint": "property_hint",
                "ambiguous": "ambiguous",
                "context": "context",
            },
        )
        sql, params = build_insert(mapping, self.obs)
        self.assertIn('INSERT INTO "observations"', sql)
        self.assertEqual(len(params), 10)

        self.assertEqual(insert_sqlite(self.con, self.obs, mapping), 1)
        row = self.con.execute(
            "SELECT source_id,value,unit,subject_hint,property_hint FROM observations"
        ).fetchone()
        self.assertEqual(row, ("manual-1", "500", "W", "Base", "Rated power"))


if __name__ == "__main__":
    unittest.main()
