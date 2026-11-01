import tempfile
from pathlib import Path
import unittest

from evidencemill.benchmark import benchmark_paths


class BenchmarkTests(unittest.TestCase):
    def test_benchmark_runs_document_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.md"
            path.write_text(
                "# Drive\nThe scooter uses dual 500 W motors with a combined peak output of 2400 W.\n",
                encoding="utf-8",
            )
            result = benchmark_paths([path], repeats=2)
        self.assertEqual(result.documents_per_run, 1)
        self.assertEqual(result.candidates_per_run, 2)
        self.assertGreaterEqual(result.ready_per_run, 1)
        self.assertGreater(result.median_candidates_per_second, 0)


if __name__ == "__main__":
    unittest.main()
