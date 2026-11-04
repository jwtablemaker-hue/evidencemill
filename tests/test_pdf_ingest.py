import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import fitz
    import pytesseract
except ImportError:
    fitz = None

from evidencemill.document import TextBlock
from evidencemill.ingest.pdf import parse_pdf, _ocr_regions
from evidencemill.worker import FactPrepWorker


OCR = "Specifications\nRated voltage 10.8V\nRated capacity 5.2Ah\nRated power 30W\nMax. power 40W"


@unittest.skipIf(fitz is None, "requires PDF and OCR extras")
class PdfOcrTests(unittest.TestCase):
    def parse(self, native, ocr, *, enabled=True, tables=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sparse.pdf"
            with fitz.open() as pdf:
                page = pdf.new_page()
                if native:
                    page.insert_text((72, 72), native)
                pdf.save(path)
            with patch("pytesseract.image_to_string", return_value=ocr) as read:
                if tables is None:
                    result = parse_pdf(path, ocr_scanned=enabled)
                else:
                    with patch.object(fitz.Page, "find_tables", return_value=tables):
                        result = parse_pdf(path, ocr_scanned=enabled)
            return result, read.call_count

    def text(self, document):
        return " ".join(b.text for b in document.blocks if isinstance(b, TextBlock))

    def test_sparse_native_uses_richer_ocr_and_keeps_missing_label_once(self):
        document, calls = self.parse("ES1", OCR)
        self.assertEqual(calls, 1)
        self.assertIn("Rated capacity 5.2Ah", self.text(document))
        self.assertEqual(self.text(document).count("ES1"), 1)
        candidates = FactPrepWorker().run_document(document).candidates
        self.assertEqual(sum(c.source.raw_text == "ES1" for c in candidates), 1)

    def test_label_already_in_ocr_is_not_supplemented(self):
        document, _ = self.parse("ES1", OCR + "\nES1")
        self.assertEqual(self.text(document).count("ES1"), 1)
        self.assertEqual(len(document.blocks), 1)

    def test_partial_native_block_keeps_only_missing_line(self):
        document, _ = self.parse("ES1\nNative note", OCR + "\nES1")
        self.assertEqual(self.text(document).count("ES1"), 1)
        self.assertEqual(self.text(document).count("Native note"), 1)

    def test_substantial_native_does_not_invoke_ocr(self):
        native = "The manual contains substantial native text already available for extraction."
        document, calls = self.parse(native, OCR)
        self.assertEqual(calls, 0)
        self.assertEqual(self.text(document), native)

    def test_unhelpful_ocr_keeps_native_blocks(self):
        for ocr in ("", "ES1", "Specifications", "X" * 40):
            native = "ES1" if ocr != "X" * 40 else "N" * 30
            with self.subTest(ocr=ocr):
                document, calls = self.parse(native, ocr)
                self.assertEqual(calls, 1)
                self.assertEqual(self.text(document), native)
                self.assertEqual(document.blocks[0].kind, "paragraph")

    def test_ocr_preserves_blank_line_paragraphs_and_joins_wrapped_lines(self):
        ocr = (
            "Battery maintenance\n\n"
            "1. Use original battery packs;\n\n"
            "5. After every use, fully charge the battery\n"
            "to prolong its lifespan."
        )
        document, calls = self.parse("", ocr)
        self.assertEqual(calls, 1)
        blocks = [b for b in document.blocks if isinstance(b, TextBlock)]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(
            blocks[0].text,
            "Battery maintenance\n\n"
            "1. Use original battery packs;\n\n"
            "5. After every use, fully charge the battery to prolong its lifespan.",
        )
        candidates = FactPrepWorker().run_document(document).candidates
        statements = [
            c.source.raw_text for c in candidates
            if c.observation_kind == "statement"
        ]
        self.assertIn("Battery maintenance", statements)
        self.assertIn("After every use, fully charge the battery to prolong its lifespan.", statements)

    def test_spurious_blank_line_inside_sentence_is_rejoined(self):
        ocr = (
            "The damage caused by prolonged no charge is irreversible. "
            "Once the damage is done, the\n\n"
            "battery can not be recharged."
        )
        document, calls = self.parse("", ocr)
        self.assertEqual(calls, 1)
        blocks = [b for b in document.blocks if isinstance(b, TextBlock)]
        self.assertEqual(
            blocks[0].text,
            "The damage caused by prolonged no charge is irreversible. "
            "Once the damage is done, the battery can not be recharged.",
        )
        statements = [
            c.source.raw_text
            for c in FactPrepWorker().run_document(document).candidates
            if c.observation_kind == "statement"
        ]
        self.assertIn(
            "Once the damage is done, the battery can not be recharged.",
            statements,
        )

    def test_textless_page_keeps_short_ocr(self):
        document, calls = self.parse("", "ES1")
        self.assertEqual(calls, 1)
        self.assertEqual(self.text(document), "ES1")

    def test_ocr_disabled(self):
        document, calls = self.parse("ES1", OCR, enabled=False)
        self.assertEqual(calls, 0)
        self.assertEqual(self.text(document), "ES1")

    def test_meaningful_table_suppresses_ocr(self):
        from types import SimpleNamespace
        table = SimpleNamespace(extract=lambda: [["Power", "30 W"]], bbox=None)
        document, calls = self.parse("ES1", OCR, tables=SimpleNamespace(tables=[table]))
        self.assertEqual(calls, 0)
        self.assertEqual(self.text(document), "ES1")

    def parse_landscape(self, gutter):
        from PIL import Image, ImageDraw
        from io import BytesIO
        image = Image.new("RGB", (800, 400), "white")
        draw = ImageDraw.Draw(image)
        # Raster content ensures native extraction remains only the ES1 label.
        for y in range(50, 350, 20):
            if gutter:
                draw.rectangle((50, y, 350, y + 4), fill="black")
                draw.rectangle((450, y, 750, y + 4), fill="black")
            else:
                draw.rectangle((50, y, 750, y + 4), fill="black")
        stream = BytesIO()
        image.save(stream, format="PNG")
        seen = []

        def read(region):
            seen.append(region.size)
            return ("The complete left answer ends with 110 pounds [50 kg]." if len(seen) == 1
                    else "E-mail Service: support@hiboy.com. ES1")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "landscape.pdf"
            with fitz.open() as pdf:
                page = pdf.new_page(width=800, height=400)
                page.insert_image(page.rect, stream=stream.getvalue())
                page.insert_text((20, 20), "ES1")
                pdf.save(path)
            with patch("pytesseract.image_to_string", side_effect=read):
                document = parse_pdf(path, ocr_scanned=True)
        return document, seen

    def test_gutter_preserves_separate_left_right_blocks_at_4x(self):
        document, seen = self.parse_landscape(gutter=True)
        blocks = [b for b in document.blocks if isinstance(b, TextBlock)]
        self.assertEqual(seen, [(1600, 1600), (1600, 1600)])
        self.assertEqual(len(blocks), 2)
        self.assertIn("110 pounds [50 kg]", blocks[0].text)
        self.assertNotIn("E-mail", blocks[0].text)
        self.assertTrue(blocks[1].text.startswith("E-mail"))
        self.assertEqual([b.bbox for b in blocks], [(0, 0, 400, 400), (400, 0, 800, 400)])
        self.assertEqual(self.text(document).count("ES1"), 1)

    def test_landscape_without_gutter_uses_one_4x_region(self):
        document, seen = self.parse_landscape(gutter=False)
        self.assertEqual(seen, [(3200, 1600)])
        blocks = [b for b in document.blocks if isinstance(b, TextBlock)]
        self.assertEqual(sum(b.kind == "ocr_paragraph" for b in blocks), 1)
        self.assertEqual(self.text(document).count("ES1"), 1)

    def test_blank_landscape_and_one_sided_content_are_not_gutters(self):
        from PIL import Image, ImageDraw
        image = Image.new("RGB", (800, 400), "white")
        self.assertEqual(_ocr_regions(image), [(0, 0, 800, 400)])
        ImageDraw.Draw(image).rectangle((50, 50, 350, 350), fill="black")
        self.assertEqual(_ocr_regions(image), [(0, 0, 800, 400)])


if __name__ == "__main__":
    unittest.main()
