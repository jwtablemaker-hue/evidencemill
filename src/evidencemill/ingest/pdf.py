from __future__ import annotations

from math import ceil
from pathlib import Path
import re
from statistics import median

from evidencemill.document import Document, FigureBlock, TableBlock, TextBlock


def _looks_like_continuation(previous: str, following: str) -> bool:
    """Reject OCR blank lines only when the next fragment clearly continues."""
    if not previous or not following:
        return False
    if previous.rstrip().endswith((".", "!", "?", ";", ":")):
        return False
    first = following.lstrip()[:1]
    return bool(first and first.islower())


def _normalize_text_preserving_paragraphs(value: str) -> str:
    """Collapse wrapped lines while retaining defensible paragraph boundaries."""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    raw_paragraphs = []
    for paragraph in re.split(r"\n\s*\n+", text):
        joined = " ".join(
            " ".join(line.split())
            for line in paragraph.splitlines()
            if line.strip()
        ).strip()
        if joined:
            raw_paragraphs.append(joined)

    paragraphs: list[str] = []
    for paragraph in raw_paragraphs:
        if paragraphs and _looks_like_continuation(paragraphs[-1], paragraph):
            paragraphs[-1] = f"{paragraphs[-1]} {paragraph}"
        else:
            paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


def _ocr_text_with_layout(image, pytesseract) -> str:
    """Reconstruct OCR text while preserving defensible visual boundaries.

    Tesseract can flatten two nearby labels into one text line. For a one-line
    OCR block only, an unusually large horizontal word gap is retained as a
    paragraph boundary. Multi-line blocks are left intact so ordinary wrapping
    and columnar text are not over-segmented.
    """
    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
    )
    rows = []
    for index, raw in enumerate(data.get("text", ())):
        text = str(raw).strip()
        if not text:
            continue
        rows.append({
            "text": text,
            "left": int(data["left"][index]),
            "top": int(data["top"][index]),
            "width": int(data["width"][index]),
            "height": int(data["height"][index]),
            "block": int(data["block_num"][index]),
            "par": int(data["par_num"][index]),
            "line": int(data["line_num"][index]),
        })
    if not rows:
        return ""

    by_key = {}
    order = []
    for row in rows:
        key = (row["block"], row["par"], row["line"])
        if key not in by_key:
            by_key[key] = []
            order.append(key)
        by_key[key].append(row)

    lines = [
        (key, sorted(by_key[key], key=lambda item: item["left"]))
        for key in order
    ]
    block_line_counts = {}
    for key, _ in lines:
        block_line_counts[key[0]] = block_line_counts.get(key[0], 0) + 1

    rendered = []
    for key, words in lines:
        split_at = set()
        if block_line_counts.get(key[0]) == 1 and len(words) >= 4:
            gaps = [
                words[i + 1]["left"] - (words[i]["left"] + words[i]["width"])
                for i in range(len(words) - 1)
            ]
            positive = [gap for gap in gaps if gap > 0]
            heights = [word["height"] for word in words if word["height"] > 0]
            if positive and heights:
                typical_gap = median(positive)
                typical_height = median(heights)
                threshold = max(24.0, 3.0 * typical_gap, 1.25 * typical_height)
                for i, gap in enumerate(gaps):
                    left_count = i + 1
                    right_count = len(words) - left_count
                    if gap >= threshold and left_count >= 2 and right_count >= 2:
                        split_at.add(i)

        segments = []
        current = []
        for i, word in enumerate(words):
            current.append(word["text"])
            if i in split_at:
                segments.append(" ".join(current))
                current = []
        if current:
            segments.append(" ".join(current))
        rendered.append((key[0], key[1], segments))

    paragraphs = []
    active_key = None
    active_lines = []
    for block, par, segments in rendered:
        key = (block, par)
        if key != active_key:
            if active_lines:
                paragraphs.append(" ".join(active_lines))
            active_key = key
            active_lines = []
        if len(segments) > 1:
            if active_lines:
                paragraphs.append(" ".join(active_lines))
                active_lines = []
            paragraphs.extend(segment for segment in segments if segment)
            active_key = None
        elif segments:
            active_lines.append(segments[0])
    if active_lines:
        paragraphs.append(" ".join(active_lines))

    return _normalize_text_preserving_paragraphs("\n\n".join(paragraphs))


def _bbox(value):
    return tuple(float(x) for x in value) if value is not None else None


def _split_halves(image):
    width, height = image.size
    midpoint = width // 2
    return [(0, 0, midpoint, height), (midpoint, 0, width, height)]


def _ocr_regions(image):
    """Split only wide images with a blank center and content on both sides.

    Inspect a small grayscale copy; OCR still receives the full-resolution crops.
    A landscape aspect ratio alone is not evidence of a two-page spread.
    """
    width, height = image.size
    whole = (0, 0, width, height)
    if width < 1.5 * height:
        return [whole]
    sample = image.convert("L")
    sample.thumbnail((1100, 1100))
    sw, sh = sample.size

    def ink_fraction(left, right):
        histogram = sample.crop((
            int(sw * left), int(sh * .05), int(sw * right), int(sh * .95),
        )).histogram()
        return sum(histogram[:200]) / max(1, sum(histogram))

    center = ink_fraction(.49, .51)
    surrounding = min(ink_fraction(.10, .45), ink_fraction(.55, .90))
    if surrounding >= .01 and center <= .005 and center <= .1 * surrounding:
        return _split_halves(image)
    return [whole]


def _wide_page_geometry(page):
    width = float(page.rect.width)
    height = float(page.rect.height)
    if height <= 0 or width < 1.5 * height:
        return None
    return (round(width, 1), round(height, 1))


def _page_has_two_up_gutter(page, fitz, Image):
    """Probe page layout cheaply; this does not OCR or alter source evidence."""
    width = max(float(page.rect.width), 1.0)
    scale = min(2.0, 1100.0 / width)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return len(_ocr_regions(image)) == 2


def _infer_document_two_up_geometries(doc, fitz, Image):
    """Infer repeated two-up sheet geometry from conservative gutter evidence.

    A center-crossing title, diagram, or artwork can hide the gutter on an
    individual sheet. When at least 60% of four or more same-sized wide sheets
    independently show the two-up gutter, treat that repeated sheet geometry as
    two-up for OCR reading order. This is document-local evidence only.
    """
    groups = {}
    for page in doc:
        geometry = _wide_page_geometry(page)
        if geometry is not None:
            groups.setdefault(geometry, []).append(page)

    inferred = set()
    for geometry, pages in groups.items():
        if len(pages) < 4:
            continue
        if len(pages) > 24:
            last = len(pages) - 1
            indices = sorted({round(i * last / 23) for i in range(24)})
            sample = [pages[index] for index in indices]
        else:
            sample = pages
        votes = sum(
            _page_has_two_up_gutter(page, fitz, Image)
            for page in sample
        )
        required = max(3, ceil(0.60 * len(sample)))
        if votes >= required:
            inferred.add(geometry)
    return inferred


def _center_inside(
    block_bbox: tuple[float, float, float, float],
    target_bbox: tuple[float, float, float, float],
) -> bool:
    x0, y0, x1, y1 = block_bbox
    tx0, ty0, tx1, ty1 = target_bbox
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    return tx0 <= cx <= tx1 and ty0 <= cy <= ty1


def parse_pdf(path: str | Path, *, source_id: str | None = None, ocr_scanned: bool = False) -> Document:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDF ingestion requires the 'pdf' extra") from exc

    p = Path(path)
    doc = fitz.open(p)
    source = source_id or p.name
    blocks = []
    counter = 0
    inferred_two_up_geometries = None
    two_up_ocr_pages = []

    for page_index, page in enumerate(doc):
        page_no = page_index + 1

        detected_tables: list[
            tuple[list[list[str | None]], tuple[float, float, float, float] | None]
        ] = []
        finder = getattr(page, "find_tables", None)
        if callable(finder):
            try:
                tables = finder().tables
            except Exception:
                tables = ()
            for table in tables:
                rows = table.extract()
                if not rows:
                    continue
                detected_tables.append((rows, _bbox(getattr(table, "bbox", None))))

        raw_blocks = page.get_text("blocks", sort=True)
        native_text = "".join("".join(str(item[4]).split()) for item in raw_blocks)
        native_count = len(native_text)
        # PDFs with broken character maps may contain many glyphs but little
        # readable text. Keep their native lines as evidence below.
        controls = sum(not char.isprintable() for char in native_text)
        corrupt_text = controls >= 8 and controls * 4 >= native_count
        meaningful_tables = any(
            str(cell).strip() for rows, _ in detected_tables
            for row in rows for cell in row if cell is not None
        )
        if (native_count <= 32 or corrupt_text) and not meaningful_tables and ocr_scanned:
            try:
                from PIL import Image
                import pytesseract
            except ImportError as exc:
                raise RuntimeError("scanned-page OCR requires the 'ocr' extra") from exc
            if inferred_two_up_geometries is None:
                inferred_two_up_geometries = _infer_document_two_up_geometries(
                    doc, fitz, Image
                )
            pix = page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            regions = _ocr_regions(image)
            geometry = _wide_page_geometry(page)
            if (
                geometry in inferred_two_up_geometries
                and len(regions) == 1
            ):
                regions = _split_halves(image)
            if len(regions) == 2:
                two_up_ocr_pages.append(page_no)
            region_texts = [
                (
                    region,
                    _normalize_text_preserving_paragraphs(
                        _ocr_text_with_layout(image.crop(region), pytesseract)
                    ),
                )
                for region in regions
            ]
            ocr_count = sum(len("".join(text.split())) for _, text in region_texts)
            # Keep the existing textless-page fallback, even for a short OCR result.
            richer = ocr_count >= native_count + 32 and ocr_count >= 2 * native_count
            readable_replacement = corrupt_text and ocr_count >= max(32, native_count - controls)
            if ocr_count and (native_count == 0 or richer or readable_replacement):
                for (x0, y0, x1, y1), text in region_texts:
                    if not text:
                        continue
                    counter += 1
                    blocks.append(TextBlock(
                        text=text,
                        block_id=f"text-{counter}",
                        kind="ocr_layout_review" if corrupt_text else "ocr_paragraph",
                        page=page_no,
                        bbox=(
                            x0 * page.rect.width / pix.width,
                            y0 * page.rect.height / pix.height,
                            x1 * page.rect.width / pix.width,
                            y1 * page.rect.height / pix.height,
                        ),
                    ))
                # OCR is primary. Retain native lines absent from it, without
                # emitting a second copy of lines OCR already reproduced.
                remaining = []
                for item in raw_blocks:
                    missing = []
                    for line in str(item[4]).splitlines():
                        line = " ".join(line.split())
                        if line and not any(re.search(
                            r"(?<!\w)" + re.escape(line) + r"(?!\w)",
                            text, flags=re.IGNORECASE,
                        ) for _, text in region_texts):
                            missing.append(line)
                    if missing:
                        remaining.append((*item[:4], "\n".join(missing), *item[5:]))
                raw_blocks = remaining

        table_bboxes = [bbox for _, bbox in detected_tables if bbox is not None]
        for item in raw_blocks:
            x0, y0, x1, y1, text, *_ = item
            block_bbox = (float(x0), float(y0), float(x1), float(y1))
            if any(_center_inside(block_bbox, table_bbox) for table_bbox in table_bboxes):
                continue
            text = _normalize_text_preserving_paragraphs(str(text))
            if not text:
                continue
            counter += 1
            blocks.append(TextBlock(
                text=text,
                block_id=f"text-{counter}",
                kind="paragraph",
                page=page_no,
                bbox=block_bbox,
            ))

        for rows, table_bbox in detected_tables:
            counter += 1
            blocks.append(TableBlock(
                rows=tuple(
                    tuple("" if cell is None else str(cell).strip() for cell in row)
                    for row in rows
                ),
                block_id=f"table-{counter}",
                page=page_no,
                bbox=table_bbox,
                header_rows=None,
                layout="auto",
            ))

        for image in page.get_images(full=True):
            xref = image[0]
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = ()
            if not rects:
                rects = (None,)
            for rect in rects:
                counter += 1
                blocks.append(FigureBlock(
                    block_id=f"figure-{counter}",
                    page=page_no,
                    bbox=_bbox(rect),
                    source_path=f"{p}#page={page_no}&xref={xref}",
                ))

    metadata = dict(doc.metadata or {})
    title = metadata.get("title") or None
    page_count = doc.page_count
    if inferred_two_up_geometries:
        metadata["ocr_two_up_inferred_geometries"] = [
            list(geometry) for geometry in sorted(inferred_two_up_geometries)
        ]
    if two_up_ocr_pages:
        metadata["ocr_two_up_pages"] = list(dict.fromkeys(two_up_ocr_pages))
    doc.close()
    metadata["page_count"] = page_count
    return Document(source_id=source, title=title, blocks=tuple(blocks), metadata=metadata)
