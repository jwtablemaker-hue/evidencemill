import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from evidencemill.cli import main


class CliFactsOnlyTests(unittest.TestCase):
    def test_facts_only_omits_observation_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.md"
            path.write_text(
                "# Drive\nRated motor power is 500 W.\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([str(path), "--facts-only"])

        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertIn("fact_candidates", payload)
        self.assertIn("worker_report", payload)
        self.assertNotIn("observations", payload)


if __name__ == "__main__":
    unittest.main()
