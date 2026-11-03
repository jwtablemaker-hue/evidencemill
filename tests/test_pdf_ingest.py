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
from evidencemill.ingest.pdf import parse_pdf
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


if __name__ == "__main__":
    unittest.main()
