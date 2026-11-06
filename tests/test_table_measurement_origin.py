import unittest

from evidencemill.document import Document, TableBlock
from evidencemill.pipeline import process_document


class TableMeasurementOriginTests(unittest.TestCase):
    def observations(
        self,
        value,
        header="72V40Ah(LG M50LT) / 72V32Ah",
        property_label="Material",
        section="Suspension",
    ):
        return process_document(Document(source_id="retained-manual", blocks=(
            TableBlock(block_id="table-47", page=6, rows=(
                ("Section", "Property", header),
                (section, property_label, value),
            ), header_rows=1, layout="matrix"),
        )))

    def test_configuration_header_is_context_not_property(self):
        observations = self.observations("Rubber")
        self.assertEqual([x for x in observations if x.kind == "measurement"], [])
        cells = [
            x for x in observations
            if x.kind == "table_cell" and x.value == "Rubber"
        ]
        self.assertEqual(len(cells), 1)
        cell = cells[0]
        self.assertEqual(cell.property_hint, "Material")
        self.assertEqual(cell.source.raw_text, "Material: Rubber")
        self.assertEqual(cell.context["section_heading"], "Suspension")
        self.assertEqual(
            cell.context["value_column_header"],
            "72V40Ah(LG M50LT) / 72V32Ah",
        )
        self.assertEqual(cell.context["table_layout"], "grouped_properties")

    def test_only_value_numbers_land_with_original_evidence(self):
        measurements = [
            x for x in self.observations(
                "50 psi",
                property_label="Tire Pressure",
                section="Tire",
            )
            if x.kind == "measurement"
        ]
        self.assertEqual([(x.value, x.unit) for x in measurements], [(50.0, "psi")])
        measurement = measurements[0]
        self.assertEqual(measurement.source.raw_text, "Tire Pressure: 50 psi")
        self.assertEqual(measurement.source.location, "page-6:table-47:r2c3:m1")
        self.assertEqual(measurement.context["table_property"], "Tire Pressure")
        self.assertEqual(measurement.context["table_section"], "Tire")
        self.assertEqual(
            measurement.context["table_value_header"],
            "72V40Ah(LG M50LT) / 72V32Ah",
        )
        self.assertNotIn("72V40Ah", measurement.context["statement"])
        self.assertEqual(
            len(measurement.context["statement_structure"]["measurements"]),
            1,
        )

    def test_spaced_parallel_values_preserve_positional_configuration_context(self):
        observations = self.observations(
            "Around 125km / Around 100km",
            property_label="Range",
            section="Battery",
        )
        measurements = [
            item for item in observations
            if item.kind == "measurement"
        ]
        self.assertEqual(
            [(item.value, item.unit) for item in measurements],
            [(125.0, "km"), (100.0, "km")],
        )
        self.assertEqual(
            [item.context["table_parallel_header_part"] for item in measurements],
            ["72V40Ah(LG M50LT)", "72V32Ah"],
        )
        self.assertEqual(
            [item.context["table_parallel_value_part"] for item in measurements],
            ["Around 125km", "Around 100km"],
        )
        self.assertEqual(
            [item.context["table_parallel_position"] for item in measurements],
            [1, 2],
        )
        self.assertTrue(
            all(
                item.context["table_parallel_alignment"] == "positional_candidate"
                for item in measurements
            )
        )

    def test_compact_slash_expression_is_not_claimed_as_parallel_configuration(self):
        observations = self.observations(
            "100-120V/200-240V",
            property_label="Input Voltage",
            section="Charger",
        )
        measurements = [
            item for item in observations
            if item.kind == "measurement"
        ]
        self.assertTrue(measurements)
        self.assertTrue(
            all(
                "table_parallel_alignment" not in item.context
                for item in measurements
            )
        )

    def test_numeric_header_does_not_block_inherited_value_unit(self):
        measurements = [
            x for x in self.observations(
                "50",
                "72V battery pressure (psi)",
                property_label="Tire Pressure",
                section="Tire",
            )
            if x.kind == "measurement"
        ]
        self.assertEqual([(x.value, x.unit) for x in measurements], [(50.0, "psi")])


if __name__ == "__main__":
    unittest.main()
