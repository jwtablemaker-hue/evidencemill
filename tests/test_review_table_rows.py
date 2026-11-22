from types import SimpleNamespace
import unittest

from evidencemill.review_table_rows import row_suggestions


class TableReviewTest(unittest.TestCase):
    def setUp(self):
        self.table = SimpleNamespace(rows=[
            SimpleNamespace(cells=[(0, 0, 10, 10), (10, 0, 30, 20)]),
            SimpleNamespace(cells=[(0, 10, 10, 20), None]),
        ])
        self.words = [(11, 2, 20, 9, "120–200cm"), (1, 12, 9, 19, "Wheelbase"),
                      (11, 12, 20, 19, "970mm")]

    def test_adjacent_label_recovers_lower_line_with_coordinates(self):
        result, = row_suggestions(self.table, self.words)
        self.assertEqual(result["row_label"], "Wheelbase")
        self.assertEqual(result["candidate_value"], "970mm")
        self.assertEqual(result["value_region"], (10, 10, 30, 20))

    def test_word_crossing_boundary_is_held(self):
        self.words[2] = (11, 9, 20, 19, "970mm")
        self.assertEqual(list(row_suggestions(self.table, self.words)), [])


