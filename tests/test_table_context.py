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

    def test_headerless_continuation_keeps_battery_capacity_first_row(self):
        rows = [
            ["", "Battery capacity", "72V 35Ah"],
            ["", "Motor power", "2500W*2"],
            ["", "Tire pressure", "50 psi"],
        ]
        cells = parse_table(rows, source_id="manual", location="page-6:table-47")
        capacity = next(c for c in cells if c.property_hint == "Battery capacity")
        self.assertEqual(capacity.value, "72V 35Ah")
        self.assertEqual(capacity.source.location, "page-6:table-47:r1c3")
        self.assertEqual(capacity.source.raw_text, "Battery capacity: 72V 35Ah")
        self.assertEqual(capacity.context["row_index"], 0)
        self.assertEqual(capacity.subject_hint, None)

    def test_matrix_with_numeric_model_header_stays_headered(self):
        rows = [
            ["Model", "Rated power (W)", "Peak power (W)"],
            ["Base", "500", "1000"],
        ]
        cells = parse_table(rows, source_id="manual")
        self.assertEqual(len(cells), 2)
        self.assertEqual(cells[0].property_hint, "Rated power")
        self.assertEqual(cells[0].value, "500")

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
