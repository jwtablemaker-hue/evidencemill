import unittest

from evidencemill.document import Document, TableBlock, TextBlock
from evidencemill.ingest.text import parse_text
from evidencemill.pipeline import process_document, split_sentences
from evidencemill.worker import FactPrepWorker


class DocumentPipelineTests(unittest.TestCase):
    def test_shared_scope_and_model_specific_exception(self):
        doc = Document(
            source_id="multi-model",
            metadata={
                "covered_models": ["X7", "X7PRO"],
                "model_scopes": {"X7PRO controls": ["X7PRO"]},
            },
            blocks=(
                TableBlock(
                    rows=(("Battery", "48 V"), ("Capacity", "21 Ah")),
                    block_id="shared", layout="key_value",
                ),
                TextBlock(
                    text="NFC unlocking is supported.",
                    block_id="pro", heading_path=("X7PRO controls",),
                ),
            ),
        )
        observations = process_document(doc)
        shared = [x for x in observations if x.kind == "table_cell"]
        self.assertEqual(len(shared), 2)
        self.assertTrue(all(x.context["applicable_models"] == ["X7", "X7PRO"] for x in shared))
        self.assertTrue(all(x.context["applicability_basis"] == "document_coverage" for x in shared))
        pro = next(x for x in observations if x.kind == "statement")
        self.assertEqual(pro.context["applicable_models"], ["X7PRO"])
        self.assertEqual(pro.context["applicability_basis"], "explicit_section_scope")

    def test_other_model_names_and_unresolved_coverage(self):
        for models in (["Alpha", "Beta", "Gamma"], ["A1", "A1 Plus"]):
            doc = Document(
                source_id="manual",
                metadata={"covered_models": models},
                blocks=(TextBlock(text="Check tire pressure.", block_id="p1"),),
            )
            self.assertEqual(
                process_document(doc)[0].context["applicable_models"], models
            )
        doc = Document(
            source_id="unknown",
            blocks=(TextBlock(text="Check tire pressure.", block_id="p1"),),
        )
        self.assertNotIn("applicable_models", process_document(doc)[0].context)

    def test_discovers_explicit_model_enumerations(self):
        for title in ("Models: X7/X7PRO", "Models: Alpha, Beta and Gamma"):
            doc = Document(
                source_id="manual",
                title=title,
                blocks=(TextBlock(text="Inspect the brake.", block_id="p1"),),
            )
            result = process_document(doc)
            self.assertGreaterEqual(len(result[0].context["applicable_models"]), 2)
            self.assertEqual(result[0].context["applicability_basis"], "explicit_model_enumeration")

    def test_discovers_multi_model_manual_title(self):
        doc = Document(
            source_id="manual",
            title="X7/X7PRO User Manual",
            blocks=(TextBlock(text="Inspect the brake.", block_id="p1"),),
        )
        result = process_document(doc)[0]
        self.assertEqual(result.context["applicable_models"], ["X7", "X7PRO"])
        self.assertEqual(result.context["applicability_basis"], "manual_title_coverage")

    def test_pdf_cover_title_without_pdf_metadata(self):
        doc = Document(
            source_id="manual.pdf",
            blocks=(
                TextBlock(text="X7/X7PRO User Manual", block_id="cover", page=1),
                TableBlock(rows=(("Battery", "48 V"),), block_id="specs", page=18, layout="key_value"),
            ),
        )
        specs = next(item for item in process_document(doc) if item.kind == "table_cell")
        self.assertEqual(specs.context["applicable_models"], ["X7", "X7PRO"])
        self.assertEqual(specs.context["applicability_basis"], "manual_title_coverage")

    def test_does_not_infer_from_ambiguous_title(self):
        doc = Document(
            source_id="manual",
            title="X7/X7PRO parts discussion",
            blocks=(TextBlock(text="Inspect the brake.", block_id="p1"),),
        )
        self.assertNotIn("applicable_models", process_document(doc)[0].context)

    def test_automatic_section_narrowing_preserves_shared_specs(self):
        doc = Document(
            source_id="manual",
            title="X7/X7PRO User Manual",
            blocks=(
                TableBlock(
                    rows=(("Voltage", "48 V"),),
                    block_id="specs", layout="key_value",
                ),
                TextBlock(
                    text="Use the NFC card.",
                    block_id="controls", heading_path=("X7PRO controls",),
                ),
            ),
        )
        result = process_document(doc)
        shared = next(x for x in result if x.kind == "table_cell")
        specific = next(x for x in result if x.kind == "statement")
        self.assertEqual(shared.context["applicable_models"], ["X7", "X7PRO"])
        self.assertEqual(specific.context["applicable_models"], ["X7PRO"])
        self.assertEqual(specific.context["applicability_basis"], "section_model_mention")

    def test_model_specific_table_scope(self):
        doc = Document(
            source_id="manual",
            title="Models: Alpha, Beta",
            blocks=(
                TableBlock(
                    rows=(("NFC", "Yes"),),
                    block_id="beta-controls", layout="key_value",
                    subject_hint="Beta controls",
                ),
            ),
        )
        result = process_document(doc)
        cell = next(item for item in result if item.kind == "table_cell")
        self.assertEqual(cell.context["applicable_models"], ["Beta"])
        self.assertEqual(cell.context["applicability_basis"], "table_model_mention")

    def test_scope_survives_fact_prep_worker(self):
        doc = Document(
            source_id="manual.pdf",
            blocks=(
                TextBlock(text="X7/X7PRO User Manual", block_id="cover", page=1),
                TableBlock(
                    rows=(("Battery capacity", "21 Ah"),),
                    block_id="specifications", page=18, layout="key_value",
                ),
                TextBlock(
                    text="NFC unlocking is supported.",
                    block_id="pro-controls", page=9,
                    heading_path=("X7PRO controls",),
                ),
            ),
        )
        result = FactPrepWorker().run_document(doc)
        shared = [
            candidate for candidate in result.candidates
            if candidate.observation_kind == "measurement"
        ]
        self.assertTrue(shared)
        self.assertEqual(shared[0].context["applicable_models"], ["X7", "X7PRO"])
        pro = next(
            candidate for candidate in result.candidates
            if "NFC unlocking" in str(candidate.value)
        )
        self.assertEqual(pro.context["applicable_models"], ["X7PRO"])

    def test_invalid_declared_exception_is_explicitly_held(self):
        doc = Document(
            source_id="manual",
            metadata={
                "covered_models": ["Alpha", "Beta"],
                "model_scopes": {"controls": ["Gamma"]},
            },
            blocks=(
                TextBlock(
                    text="Use the controls.",
                    block_id="controls", heading_path=("controls",),
                ),
            ),
        )
        candidate = FactPrepWorker().run_document(doc).candidates[0]
        self.assertEqual(
            candidate.context["applicability_unresolved"],
            "invalid_explicit_model_scope",
        )
        self.assertNotIn("applicable_models", candidate.context)

    def test_text_to_measurements(self):
        doc = parse_text(
            "# Drive\nThe scooter uses dual 500 W motors with a combined peak output of 2400 W.",
            source_id="sample",
        )
        observations = process_document(doc)
        measurements = [x for x in observations if x.kind == "measurement"]
        self.assertEqual(len(measurements), 2)
        self.assertEqual(measurements[0].value, 500.0)
        self.assertEqual(measurements[0].subject_hint, "motor")
        self.assertEqual(measurements[0].context["scope"], "each")
        self.assertEqual(measurements[1].value, 2400.0)
        self.assertEqual(measurements[1].context["scope"], "system")

    def test_explicit_table_reference_reaches_prose_before_sentence_analysis(self):
        doc = Document(
            source_id="manual",
            blocks=(
                TextBlock(
                    text="Table 1 lists rated voltage 48 V.",
                    block_id="prose",
                    page=3,
                ),
                TableBlock(
                    rows=(("Rated voltage", "48 V"),),
                    block_id="specs",
                    caption="Table 1 Specifications",
                    page=3,
                    layout="key_value",
                ),
            ),
        )
        observations = process_document(doc)
        statement = next(
            item for item in observations
            if item.kind == "statement" and item.source.location.endswith("prose:s1")
        )
        measurement = next(
            item for item in observations
            if item.kind == "measurement" and item.source.location.endswith("prose:s1:m1")
        )
        expected = [{
            "kind": "table",
            "label": "1",
            "target_block_id": "specs",
            "source_text": "Table 1",
        }]
        self.assertEqual(statement.context["structural_references"], expected)
        self.assertEqual(measurement.context["structural_references"], expected)

    def test_prose_voltage_does_not_crash(self):
        doc = parse_text("The motor operates at 48 V.", source_id="voltage-test")
        observations = process_document(doc)
        measurements = [item for item in observations if item.kind == "measurement"]
        self.assertEqual(len(measurements), 1)
        self.assertEqual(measurements[0].source.source_id, "voltage-test")
        self.assertEqual(measurements[0].unit, "V")

    def test_paragraph_boundaries_are_hard_sentence_boundaries(self):
        self.assertEqual(
            split_sentences(
                "Open the cover\n\n"
                "Do not connect the charger if the port is wet. "
                "Cover the port when not in use.\n\n"
                "A wrapped\nline stays together."
            ),
            (
                "Open the cover",
                "Do not connect the charger if the port is wet.",
                "Cover the port when not in use.",
                "A wrapped line stays together.",
            ),
        )


if __name__ == "__main__":
    unittest.main()
