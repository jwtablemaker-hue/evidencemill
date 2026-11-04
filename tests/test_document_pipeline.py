import unittest

from evidencemill.ingest.text import parse_text
from evidencemill.pipeline import process_document, split_sentences


class DocumentPipelineTests(unittest.TestCase):
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
