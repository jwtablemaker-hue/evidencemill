import unittest

from evidencemill.document import Document, TableBlock
from evidencemill.pipeline import process_document


class TableMeasurementOriginTests(unittest.TestCase):
    def observations(self, value, header="72V40Ah(LG M50LT) / 72V32Ah"):
        return process_document(Document(source_id="retained-manual", blocks=(
            TableBlock(block_id="table-47", page=6, rows=(
                ("Section", "Property", header),
                ("Suspension", "Material", value),
            ), header_rows=1, layout="matrix"),
        )))

    def test_numeric_header_is_not_a_measurement_of_text_value(self):
        observations = self.observations("Rubber")
        self.assertEqual([x for x in observations if x.kind == "measurement"], [])
        cells = [x for x in observations if x.kind == "table_cell"]
        self.assertTrue(any(x.value == "Rubber" for x in cells))
        self.assertTrue(any("72V40Ah" in (x.property_hint or "") for x in cells))

    def test_only_value_numbers_land_with_original_evidence(self):
        measurements = [x for x in self.observations("50 psi") if x.kind == "measurement"]
        self.assertEqual([(x.value, x.unit) for x in measurements], [(50.0, "psi")])
        self.assertEqual(measurements[0].source.raw_text, "50 psi")
        self.assertEqual(measurements[0].source.location, "page-6:table-47:r2c3:m1")
        self.assertIn("72V40Ah", measurements[0].context["statement"])
        self.assertEqual(len(measurements[0].context["statement_structure"]["measurements"]), 1)

    def test_numeric_header_does_not_block_inherited_value_unit(self):
        measurements = [x for x in self.observations("50", "72V battery pressure (psi)") if x.kind == "measurement"]
        self.assertEqual([(x.value, x.unit) for x in measurements], [(50.0, "psi")])
