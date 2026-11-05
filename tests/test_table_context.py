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

    def test_grouped_item_parameter_preserves_value_cell_and_section(self):

        rows = [["", "Item", "Parameter"], ["Product", "Model", "ED2301"],
                [None, "Net Weight", "51.2kg"]]
        cells = parse_table(rows, source_id="manual")
        weight = cells[-1]
        assert weight.property_hint == "Net Weight"
        assert weight.source.location == "r3c3"
        assert weight.source.raw_text == "Net Weight: 51.2kg"
        assert weight.context["section_heading"] == "Product"
        assert weight.subject_hint is None


if __name__ == "__main__":
    unittest.main()
