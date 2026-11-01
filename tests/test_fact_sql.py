import sqlite3
import unittest

from evidencemill.fact_sql import STAGING_TABLE, stage_candidates_sqlite
from evidencemill.models import SourceRef
from evidencemill.worker import FactCandidate, READY


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
        count = con.execute(f"SELECT COUNT(*) FROM {STAGING_TABLE}").fetchone()[0]
        row = con.execute(
            f"SELECT readiness,predicate_hint,value_json FROM {STAGING_TABLE}"
        ).fetchone()
        self.assertEqual(count, 1)
        self.assertEqual(row, ("READY", "rated.power", '"500"'))
        con.close()


if __name__ == "__main__":
    unittest.main()
