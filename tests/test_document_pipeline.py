import unittest

from evidencemill.document import Document, TableBlock, TextBlock
from evidencemill.ingest.text import parse_text
from evidencemill.pipeline import process_document, split_sentences


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

    def test_does_not_infer_from_ambiguous_title(self):
        doc = Document(
            source_id="manual",
            title="X7/X7PRO parts discussion",
            blocks=(TextBlock(text="Inspect the brake.", block_id="p1"),),
        )
        self.assertNotIn("applicable_models", process_document(doc)[0].context)

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
