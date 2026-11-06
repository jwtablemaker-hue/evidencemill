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


    def test_grouped_configuration_header_is_not_the_property(self):
        rows = [
            ["Section", "Property", "72V40Ah(LG M50LT) / 72V32Ah"],
            ["Battery", "Range", "Around 125km / Around 100km"],
            [None, "Duration of Charging", "28hr / 23hr"],
        ]
        cells = parse_table(rows, source_id="manual")
        self.assertEqual(len(cells), 2)
        self.assertEqual(
            [(cell.property_hint, cell.value) for cell in cells],
            [
                ("Range", "Around 125km / Around 100km"),
                ("Duration of Charging", "28hr / 23hr"),
            ],
        )
        self.assertEqual(cells[0].context["section_heading"], "Battery")
        self.assertEqual(
            cells[0].context["value_column_header"],
            "72V40Ah(LG M50LT) / 72V32Ah",
        )
        self.assertEqual(cells[0].context["table_layout"], "grouped_properties")


if __name__ == "__main__":
    unittest.main()
