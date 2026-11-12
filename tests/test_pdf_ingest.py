import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import fitz
    import pytesseract
except ImportError:
    fitz = None

from evidencemill.document import FigureBlock, OcrWord, TableBlock, TextBlock
from evidencemill.ingest.pdf import (
    parse_pdf,
    _looks_like_two_up_spread,
    _ocr_banded_table,
    _ocr_regions,
    _ocr_ruled_table,
    _ocr_text_with_layout,
)
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
            with patch("evidencemill.ingest.pdf._ocr_text_with_layout", return_value=ocr) as read:
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

    def test_broken_native_character_map_retries_ocr_and_preserves_source(self):
        native = "Assembly " + "\x01\x02A" * 40
        item = (10, 10, 250, 40, native, 0, 0)
        tables = SimpleNamespace(tables=[])
        with patch.object(fitz.Page, "get_text", return_value=[item]):
            document, calls = self.parse("", OCR, tables=tables)
        self.assertEqual(calls, 1)
        self.assertIn("Rated capacity 5.2Ah", self.text(document))
        self.assertIn(native, self.text(document))
        candidates = FactPrepWorker().run_document(document).candidates
        recovered = [c for c in candidates if c.context.get("ocr_layout_review")]
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].review_reason, "ocr_reading_order_requires_review")
        self.assertNotIn("service_instruction", recovered[0].conditions)

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

    def test_meaningful_table_does_not_suppress_page_prose_ocr(self):
        table = SimpleNamespace(
            extract=lambda: [["Power", "30 W"]],
            bbox=(50, 100, 250, 180),
        )
        document, calls = self.parse("ES1", OCR, tables=SimpleNamespace(tables=[table]))
        self.assertEqual(calls, 1)
        self.assertIn("Rated capacity 5.2Ah", self.text(document))
        tables = [block for block in document.blocks if isinstance(block, TableBlock)]
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0].rows, (("Power", "30 W"),))

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
            with patch("evidencemill.ingest.pdf._ocr_text_with_layout", side_effect=lambda region, _: read(region)):
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

    def test_very_wide_page_with_quiet_center_splits_without_document_vote(self):
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (1200, 400), "black")
        draw = ImageDraw.Draw(image)
        # Distinct content on both logical pages, plus a center-crossing label.
        for y in range(60, 340, 24):
            draw.rectangle((70, y, 470, y + 5), fill="white")
            draw.rectangle((730, y, 1130, y + 5), fill="white")
        draw.rectangle((635, 80, 648, 320), fill="white")
        self.assertTrue(_looks_like_two_up_spread(image))

    def test_true_landscape_page_is_not_split_by_relaxed_page_check(self):
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (800, 400), "white")
        draw = ImageDraw.Draw(image)
        for y in range(50, 350, 20):
            draw.rectangle((50, y, 750, y + 4), fill="black")
        self.assertFalse(_looks_like_two_up_spread(image))

    def test_page_level_two_up_detection_controls_ocr_regions(self):
        from PIL import Image, ImageDraw
        from io import BytesIO

        image = Image.new("RGB", (1200, 400), "white")
        draw = ImageDraw.Draw(image)
        for y in range(50, 350, 20):
            draw.rectangle((60, y, 480, y + 4), fill="black")
            draw.rectangle((720, y, 1140, y + 4), fill="black")
        # A narrow center mark defeats the old exact blank-gutter check.
        draw.rectangle((596, 120, 604, 280), fill="black")
        stream = BytesIO()
        image.save(stream, format="PNG")
        seen = []

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page-level-two-up.pdf"
            with fitz.open() as pdf:
                page = pdf.new_page(width=1200, height=400)
                page.insert_image(page.rect, stream=stream.getvalue())
                page.insert_text((20, 20), "ES1")
                pdf.save(path)

            def read(region):
                seen.append(region.size)
                return "Recovered OCR text contains a useful specification value of 10.8 V."

            with patch(
                "evidencemill.ingest.pdf._ocr_text_with_layout",
                side_effect=lambda region, _: read(region),
            ):
                document = parse_pdf(path, ocr_scanned=True)

        self.assertEqual(seen, [(2400, 1600), (2400, 1600)])
        self.assertEqual(document.metadata["ocr_two_up_pages"], [1])

    def test_embedded_figure_reuses_positioned_image_ocr(self):
        from PIL import Image
        from io import BytesIO

        image = Image.new("RGB", (200, 100), "white")
        stream = BytesIO()
        image.save(stream, format="PNG")
        fake_words = (
            OcrWord("1", (10, 10, 20, 20), 95.0),
            OcrWord("Motor", (40, 10, 100, 25), 96.0),
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "figure.pdf"
            with fitz.open() as pdf:
                page = pdf.new_page(width=800, height=600)
                page.insert_text(
                    (40, 40),
                    "This page contains enough native text to avoid page OCR entirely.",
                )
                page.insert_image(fitz.Rect(100, 100, 500, 300), stream=stream.getvalue())
                pdf.save(path)

            with patch(
                "evidencemill.ingest.pdf.ocr_words",
                return_value=fake_words,
            ) as read:
                document = parse_pdf(path, ocr_scanned=True)

        read.assert_called_once()
        figures = [
            block for block in document.blocks
            if isinstance(block, FigureBlock) and block.labels
        ]
        self.assertEqual(len(figures), 1)
        figure = figures[0]
        self.assertEqual([word.text for word in figure.labels], ["1", "Motor"])
        self.assertEqual(figure.callouts, ("1",))
        self.assertEqual(figure.labels[0].bbox, (120.0, 120.0, 140.0, 140.0))
        self.assertEqual(figure.labels[1].bbox, (180.0, 120.0, 300.0, 150.0))

    def test_page_sized_raster_is_not_re_ocrd_as_figure(self):
        from PIL import Image
        from io import BytesIO

        image = Image.new("RGB", (800, 600), "white")
        stream = BytesIO()
        image.save(stream, format="PNG")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page-raster.pdf"
            with fitz.open() as pdf:
                page = pdf.new_page(width=800, height=600)
                page.insert_image(page.rect, stream=stream.getvalue())
                page.insert_text(
                    (40, 40),
                    "This native text is deliberately long enough to suppress page OCR.",
                )
                pdf.save(path)
            with patch("evidencemill.ingest.pdf.ocr_words") as read:
                parse_pdf(path, ocr_scanned=True)
        read.assert_not_called()

    def test_raster_ruled_table_recovers_rows_before_prose_ocr(self):
        from PIL import Image, ImageDraw
        from io import BytesIO

        image = Image.new("RGB", (600, 400), "white")
        draw = ImageDraw.Draw(image)
        for x in (50, 190, 330, 450, 550):
            draw.line((x, 60, x, 340), fill=(220, 220, 220), width=2)
        for y in (60, 125, 230, 340):
            draw.line((50, y, 550, y), fill=(220, 220, 220), width=2)

        class FakeTesseract:
            Output = SimpleNamespace(DICT="DICT")

            @staticmethod
            def image_to_data(region, output_type, config=None):
                self.assertEqual(output_type, "DICT")
                self.assertEqual(config, "--psm 6")
                width, height = region.size
                texts = [
                    "Item", "Size", "Torque", "Qty",
                    "Deck", "M4x10mm", "2Nm", "4",
                    "Fender", "M5x12mm", "3Nm", "2",
                ]
                columns = (0.08, 0.36, 0.64, 0.86)
                rows = (0.12, 0.47, 0.78)
                left = []
                top = []
                line = []
                for row_index, y_fraction in enumerate(rows, start=1):
                    for x_fraction in columns:
                        left.append(int(width * x_fraction))
                        top.append(int(height * y_fraction))
                        line.append(row_index)
                return {
                    "text": texts,
                    "left": left,
                    "top": top,
                    "width": [max(12, int(width * .08))] * len(texts),
                    "height": [max(10, int(height * .08))] * len(texts),
                    "block_num": [1] * len(texts),
                    "par_num": [1] * len(texts),
                    "line_num": line,
                }

        recovered = _ocr_ruled_table(image, FakeTesseract)
        self.assertIsNotNone(recovered)
        rows, bbox = recovered
        self.assertEqual(
            rows,
            [
                ["Item", "Size", "Torque", "Qty"],
                ["Deck", "M4x10mm", "2Nm", "4"],
                ["Fender", "M5x12mm", "3Nm", "2"],
            ],
        )
        self.assertLessEqual(abs(bbox[0] - 50), 4)
        self.assertLessEqual(abs(bbox[2] - 550), 4)

        stream = BytesIO()
        image.save(stream, format="PNG")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ruled-table.pdf"
            with fitz.open() as pdf:
                page = pdf.new_page(width=600, height=400)
                page.insert_image(page.rect, stream=stream.getvalue())
                pdf.save(path)

            def recover(region, _):
                return _ocr_ruled_table(region, FakeTesseract)

            with patch(
                "evidencemill.ingest.pdf._ocr_ruled_table",
                side_effect=recover,
            ), patch(
                "evidencemill.ingest.pdf._ocr_text_with_layout",
                return_value="Outside prose remains.",
            ):
                document = parse_pdf(path, ocr_scanned=True)

        tables = [block for block in document.blocks if isinstance(block, TableBlock)]
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0].rows[1], ("Deck", "M4x10mm", "2Nm", "4"))
        self.assertEqual(tables[0].header_rows, 1)
        self.assertEqual(tables[0].layout, "matrix")
        self.assertEqual(document.metadata["ocr_ruled_table_pages"], [1])

    def test_ruled_table_ignores_full_height_right_edge_page_seam(self):
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (600, 400), "white")
        draw = ImageDraw.Draw(image)
        # The table ends near the logical-page edge. A full-height two-up seam
        # sits just outside it and must not redefine the table's vertical extent.
        for x in (50, 190, 330, 450, 590):
            draw.line((x, 60, x, 340), fill=(220, 220, 220), width=2)
        draw.line((599, 0, 599, 399), fill=(220, 220, 220), width=2)
        for y in (60, 125, 230, 340):
            draw.line((50, y, 590, y), fill=(220, 220, 220), width=2)

        class FakeTesseract:
            Output = SimpleNamespace(DICT="DICT")

            @staticmethod
            def image_to_data(region, output_type, config=None):
                self.assertEqual(output_type, "DICT")
                self.assertEqual(config, "--psm 6")
                width, height = region.size
                texts = [
                    "Item", "Size", "Torque", "Qty",
                    "Deck", "M4x10mm", "2Nm", "4",
                    "Fender", "M5x12mm", "3Nm", "2",
                ]
                columns = (0.08, 0.34, 0.62, 0.84)
                rows = (0.12, 0.47, 0.78)
                left = []
                top = []
                line = []
                for row_index, y_fraction in enumerate(rows, start=1):
                    for x_fraction in columns:
                        left.append(int(width * x_fraction))
                        top.append(int(height * y_fraction))
                        line.append(row_index)
                return {
                    "text": texts,
                    "left": left,
                    "top": top,
                    "width": [max(12, int(width * .08))] * len(texts),
                    "height": [max(10, int(height * .08))] * len(texts),
                    "block_num": [1] * len(texts),
                    "par_num": [1] * len(texts),
                    "line_num": line,
                }

        recovered = _ocr_ruled_table(image, FakeTesseract)
        self.assertIsNotNone(recovered)
        rows, bbox = recovered
        self.assertEqual(rows[0], ["Item", "Size", "Torque", "Qty"])
        self.assertEqual(rows[1], ["Deck", "M4x10mm", "2Nm", "4"])
        self.assertLessEqual(abs(bbox[0] - 50), 4)
        self.assertLessEqual(abs(bbox[2] - 590), 4)

    def test_banded_raster_table_requires_bands_rules_and_regular_headers(self):
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (600, 500), "white")
        draw = ImageDraw.Draw(image)
        table_left, table_right = 50, 550
        draw.line((table_left, 60, table_right, 60), fill=(220, 220, 220), width=2)
        for top, bottom in ((100, 150), (220, 270), (340, 390)):
            draw.rectangle(
                (table_left, top, table_right, bottom),
                fill=(220, 220, 220),
            )
        draw.line((table_left, 430, table_right, 430), fill=(220, 220, 220), width=2)

        class FakeTesseract:
            Output = SimpleNamespace(DICT="DICT")

            @staticmethod
            def image_to_data(region, output_type, config=None):
                self.assertEqual(output_type, "DICT")
                self.assertEqual(config, "--psm 6")
                if region.height < 100:
                    return {
                        "text": ["Every", "ride", "50km", "500km"],
                        "left": [120, 165, 300, 430],
                        "top": [12, 12, 12, 12],
                        "width": [40, 30, 45, 50],
                        "height": [18, 18, 18, 18],
                        "block_num": [1] * 4,
                        "par_num": [1] * 4,
                        "line_num": [1] * 4,
                    }

                texts = [
                    "Tires", "Check", "pressure",
                    "Brakes", "Check", "adjustment",
                    "Lights", "Inspect", "lights",
                    "Battery", "Review", "health",
                    "Wheel", "nuts", "Tighten",
                    "Fender", "screws", "Tighten",
                ]
                row_centers = [65, 125, 185, 245, 305, 365]
                left = []
                top = []
                widths = []
                heights = []
                lines = []
                for row_index, center_y in enumerate(row_centers, start=1):
                    left.extend([25, 175, 235])
                    top.extend([center_y, center_y, center_y])
                    widths.extend([70, 45, 65])
                    heights.extend([18, 18, 18])
                    lines.extend([row_index, row_index, row_index])
                return {
                    "text": texts,
                    "left": left,
                    "top": top,
                    "width": widths,
                    "height": heights,
                    "block_num": [1] * len(texts),
                    "par_num": [1] * len(texts),
                    "line_num": lines,
                }

        recovered = _ocr_banded_table(image, FakeTesseract)
        self.assertIsNotNone(recovered)
        rows, bbox = recovered
        self.assertEqual(rows[0], ["", "Every ride", "50km", "500km"])
        self.assertEqual(rows[1][0], "Tires")
        self.assertEqual(rows[2][0], "Brakes")
        self.assertGreaterEqual(len(rows), 4)
        self.assertLessEqual(abs(bbox[0] - table_left), 5)
        self.assertLessEqual(abs(bbox[2] - table_right), 5)

        unbounded = Image.new("RGB", (600, 500), "white")
        unbounded_draw = ImageDraw.Draw(unbounded)
        for top, bottom in ((100, 150), (220, 270), (340, 390)):
            unbounded_draw.rectangle(
                (table_left, top, table_right, bottom),
                fill=(220, 220, 220),
            )
        self.assertIsNone(_ocr_banded_table(unbounded, FakeTesseract))

    def test_one_line_ocr_block_splits_only_at_anomalous_word_gap(self):

        words = ["Open", "the", "rubber", "cover", "Insert", "the", "charger", "plug", "in"]
        widths = [50, 30, 60, 50, 60, 30, 70, 40, 20]
        gaps = [10, 10, 10, 40, 10, 10, 10, 10]
        lefts = [0]
        for width, gap in zip(widths[:-1], gaps):
            lefts.append(lefts[-1] + width + gap)
        data = {
            "text": words,
            "left": lefts,
            "top": [10] * len(words),
            "width": widths,
            "height": [24] * len(words),
            "block_num": [1] * len(words),
            "par_num": [1] * len(words),
            "line_num": [1] * len(words),
        }
        fake = SimpleNamespace(
            Output=SimpleNamespace(DICT="DICT"),
            image_to_data=lambda image, output_type: data,
        )
        self.assertEqual(
            _ocr_text_with_layout(object(), fake),
            "Open the rubber cover\n\nInsert the charger plug in",
        )

    def test_large_gap_in_multiline_block_is_not_forced_to_split(self):

        data = {
            "text": ["A", "wide", "gap", "here", "wrapped", "line"],
            "left": [0, 20, 70, 180, 0, 70],
            "top": [10, 10, 10, 10, 40, 40],
            "width": [10, 30, 30, 30, 50, 30],
            "height": [20] * 6,
            "block_num": [1] * 6,
            "par_num": [1] * 6,
            "line_num": [1, 1, 1, 1, 2, 2],
        }
        fake = SimpleNamespace(
            Output=SimpleNamespace(DICT="DICT"),
            image_to_data=lambda image, output_type: data,
        )
        self.assertEqual(
            _ocr_text_with_layout(object(), fake),
            "A wide gap here wrapped line",
        )

    def test_blank_landscape_and_one_sided_content_are_not_gutters(self):
        from PIL import Image, ImageDraw
        image = Image.new("RGB", (800, 400), "white")
        self.assertEqual(_ocr_regions(image), [(0, 0, 800, 400)])
        ImageDraw.Draw(image).rectangle((50, 50, 350, 350), fill="black")
        self.assertEqual(_ocr_regions(image), [(0, 0, 800, 400)])


if __name__ == "__main__":
    unittest.main()
