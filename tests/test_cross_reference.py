import unittest

from evidencemill.cross_reference import resolve_cross_references
from evidencemill.document import Document, FigureBlock, TextBlock


class CrossReferenceTests(unittest.TestCase):
    def test_resolves_figure_reference(self):
        doc = Document(
            source_id="manual",
            blocks=(
                TextBlock("See Figure 4 for wiring.", "text-1"),
                FigureBlock("fig-1", caption="Figure 4 Wiring"),
            ),
        )
        refs = resolve_cross_references(doc)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].target_block_id, "fig-1")


if __name__ == "__main__":
    unittest.main()
