import sqlite3
import unittest

from evidencemill.fact_sql import STAGING_TABLE, stage_candidates_sqlite
from evidencemill.models import SourceRef
from evidencemill.worker import FactCandidate, READY, REVIEW


class FactSqlTests(unittest.TestCase):
    def test_stage_is_idempotent(self):
        con = sqlite3.connect(":memory:")
        candidate = FactCandidate(
            candidate_id="emfc-test",
            source=SourceRef("manual", "table:r2c2", "500"),
            observation_kind="table_cell",
            subject_hint="Base",
            predicate_hint="rated.power",
            value="500",
            unit="W",
            readiness=READY,
            confidence=0.98,
        )
        stage_candidates_sqlite(con, [candidate])
        stage_candidates_sqlite(con, [candidate])
        count = con.execute(
            f"SELECT COUNT(*) FROM {STAGING_TABLE}"
        ).fetchone()[0]
        row = con.execute(
            f"SELECT readiness,predicate_hint,value_json FROM {STAGING_TABLE}"
        ).fetchone()
        self.assertEqual(count, 1)
        self.assertEqual(row, ("READY", "rated.power", '"500"'))
        con.close()

    def test_old_staging_table_gets_review_reasons_column(self):
        con = sqlite3.connect(":memory:")
        con.execute(
            "CREATE TABLE evidencemill_fact_candidates("
            "candidate_id TEXT PRIMARY KEY,"
            "source_id TEXT NOT NULL,"
            "source_location TEXT,"
            "source_text TEXT,"
            "observation_kind TEXT NOT NULL,"
            "subject_hint TEXT,"
            "predicate_hint TEXT,"
            "value_json TEXT,"
            "unit TEXT,"
            "qualifiers_json TEXT NOT NULL,"
            "conditions_json TEXT NOT NULL,"
            "context_json TEXT NOT NULL,"
            "readiness TEXT NOT NULL,"
            "review_reason TEXT,"
            "confidence REAL NOT NULL)"
        )
        candidate = FactCandidate(
            candidate_id="emfc-review",
            source=SourceRef("manual", "table:r2c2", "31V +/- 0.5V"),
            observation_kind="measurement",
            subject_hint=None,
            predicate_hint="low.voltage.protection",
            value=31.0,
            unit="V",
            readiness=REVIEW,
            review_reason="subject_unresolved",
            review_reasons=(
                "subject_unresolved",
                "tolerance_requires_semantic_handling",
            ),
            confidence=0.5,
        )
        stage_candidates_sqlite(con, [candidate])
        columns = {
            row[1]
            for row in con.execute(
                "PRAGMA table_info(evidencemill_fact_candidates)"
            )
        }
        self.assertIn("review_reasons_json", columns)
        value = con.execute(
            "SELECT review_reasons_json "
            "FROM evidencemill_fact_candidates "
            "WHERE candidate_id='emfc-review'"
        ).fetchone()[0]
        self.assertEqual(
            value,
            '["subject_unresolved","tolerance_requires_semantic_handling"]',
        )
        con.close()


if __name__ == "__main__":
    unittest.main()
