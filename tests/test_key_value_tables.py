import unittest

from evidencemill.document import Document, TableBlock
from evidencemill.pipeline import process_document
from evidencemill.table_context import infer_table_layout, parse_table
from evidencemill.worker import FactPrepWorker, REVIEW


class KeyValueTableTests(unittest.TestCase):
    def setUp(self):
        self.rows = (
            ("General information", ""),
            ("Motor", "350W Brushless"),
            ("Battery", "36V 8.0Ah 288Wh"),
            ("Charger", "42V 1.5A"),
        )

    def test_infers_headerless_property_value_shape(self):
        self.assertEqual(infer_table_layout(self.rows), ("key_value", 0))
        cells = parse_table(
            self.rows,
            source_id="manual",
            header_rows=None,
            layout="auto",
        )
        self.assertEqual(len(cells), 3)
        self.assertEqual(cells[0].property_hint, "Motor")
        self.assertEqual(cells[0].context["section_heading"], "General information")
        self.assertEqual(cells[0].source.raw_text, "Motor: 350W Brushless")

    def test_matrix_header_stays_matrix(self):
        rows = (
            ("Model", "Rated power (W)"),
            ("Base", "500"),
            ("Pro", "700"),
        )
        self.assertEqual(infer_table_layout(rows), ("matrix", 1))

    def test_model_property_row_is_not_mistaken_for_header(self):
        rows = (
            ("Model", "X8 Pro"),
            ("Max speed", "25 km/h"),
            ("Battery", "36 V 10 Ah"),
        )
        self.assertEqual(infer_table_layout(rows), ("key_value", 0))

    def test_table_rows_emit_component_measurements(self):
        doc = Document(
            source_id="manual",
            blocks=(
                TableBlock(
                    rows=self.rows,
                    block_id="table-1",
                    header_rows=None,
                    layout="auto",
                ),
            ),
        )
        observations = process_document(doc)
        measurements = [item for item in observations if item.kind == "measurement"]

        motor = [item for item in measurements if item.subject_hint == "motor"]
        battery = [item for item in measurements if item.subject_hint == "battery"]
        charger = [item for item in measurements if item.subject_hint == "charger"]

        self.assertEqual([(item.value, item.unit) for item in motor], [(350.0, "W")])
        self.assertEqual(
            [(item.value, item.unit) for item in battery],
            [(36.0, "V"), (8.0, "Ah"), (288.0, "Wh")],
        )
        self.assertEqual(
            [(item.value, item.unit) for item in charger],
            [(42.0, "V"), (1.5, "A")],
        )

    def test_unqualified_motor_power_is_not_promoted_to_rated(self):
        doc = Document(
            source_id="manual",
            blocks=(
                TableBlock(
                    rows=self.rows,
                    block_id="table-1",
                    header_rows=None,
                    layout="auto",
                ),
            ),
        )
        result = FactPrepWorker().run_document(doc)
        motor_power = [
            item for item in result.candidates
            if item.subject_hint == "motor"
            and item.unit == "W"
            and item.value == 350.0
        ]
        self.assertEqual(len(motor_power), 1)
        self.assertEqual(motor_power[0].readiness, REVIEW)
        self.assertEqual(motor_power[0].review_reason, "power_rating_unspecified")

 
    def test_measurement_keeps_explicit_row_property(self):
        rows = (
            ("General information", ""),
            ("Max speed", "25 km/h"),
            ("Low voltage protection", "31V +/- 0.5V"),
        )
        doc = Document(
            source_id="manual",
            blocks=(
                TableBlock(
                    rows=rows,
                    block_id="table-1",
                    header_rows=None,
                    layout="auto",
                ),
            ),
        )
        result = FactPrepWorker().run_document(doc)

        speed = [
            item for item in result.candidates
            if item.observation_kind == "measurement"
            and item.value == 25.0
        ][0]
        self.assertEqual(speed.predicate_hint, "maximum.speed")
        self.assertIn("subject_unresolved", speed.review_reasons)

        low_voltage = [
            item for item in result.candidates
            if item.observation_kind == "measurement"
            and item.value == 31.0
        ][0]
        self.assertEqual(low_voltage.predicate_hint, "low.voltage.protection")
        self.assertIn("subject_unresolved", low_voltage.review_reasons)
        self.assertIn(
            "tolerance_requires_semantic_handling",
            low_voltage.review_reasons,
        )


if __name__ == "__main__":
    unittest.main()
