import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from evidencemill.ingest.text import parse_text

from evidencemill.cli import main


class CliFactsOnlyTests(unittest.TestCase):
    def test_library_notice_does_not_corrupt_json(self):
        def noisy(*args, **kwargs):
            print("PDF library notice")
            return parse_text("Rated motor power is 500 W.", source_id="fixture")
        output, errors = io.StringIO(), io.StringIO()
        with patch("evidencemill.cli.ingest_path", noisy), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(main(["fixture.pdf", "--facts-only"]), 0)
        self.assertIn("fact_candidates", json.loads(output.getvalue()))
        self.assertIn("PDF library notice", errors.getvalue())

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
