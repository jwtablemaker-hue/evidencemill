import unittest

from evidencemill.document import FigureBlock, TableBlock, TextBlock
from evidencemill.ingest.html import parse_html
from evidencemill.pipeline import process_document


class HtmlIngestTests(unittest.TestCase):
    def test_extracts_headings_tables_and_figures(self):
        html = """
        <h1>Specifications</h1>
        <p>See Table 1 for ratings.</p>
        <table>
          <caption>Table 1 Power</caption>
          <tr><th>Model</th><th>Rated power (W)</th></tr>
          <tr><td>Base</td><td>500</td></tr>
        </table>
        <figure><img src="motor.png" alt="motor">
          <figcaption>Figure 2 Motor assembly</figcaption>
        </figure>
        """
        doc = parse_html(html, source_id="page")
        self.assertTrue(any(isinstance(x, TextBlock) and x.kind == "heading" for x in doc.blocks))
        self.assertTrue(any(isinstance(x, TableBlock) for x in doc.blocks))
        self.assertTrue(any(isinstance(x, FigureBlock) for x in doc.blocks))

        observations = process_document(doc)
        cells = [x for x in observations if x.kind == "table_cell"]
        self.assertEqual(len(cells), 1)
        self.assertEqual(cells[0].subject_hint, "Base")
        self.assertEqual(cells[0].property_hint, "Rated power")
        self.assertEqual(cells[0].unit, "W")

        refs = [x for x in observations if x.kind == "cross_reference"]
        self.assertEqual(len(refs), 1)
        self.assertFalse(refs[0].ambiguous)


if __name__ == "__main__":
    unittest.main()
