import unittest

from evidencemill.table_context import parse_table


class TableContextTests(unittest.TestCase):
    def test_row_column_and_unit_context(self):
        rows = [
            ["Model", "Rated power (W)", "Peak power (W)"],
            ["Base", "500", "1000"],
            ["Pro", "700", "1400"],
        ]
        observations = parse_table(rows, source_id="manual-1")
        self.assertEqual(len(observations), 4)

        first = observations[0]
        self.assertEqual(first.subject_hint, "Base")
        self.assertEqual(first.property_hint, "Rated power")
        self.assertEqual(first.value, "500")
        self.assertEqual(first.unit, "W")
        self.assertFalse(first.ambiguous)


if __name__ == "__main__":
    unittest.main()
