from __future__ import annotations

from pathlib import Path
import re

from evidencemill.document import Document, FigureBlock, TableBlock, TextBlock


_CONTINUATION_WORDS = frozenset({
    "a", "an", "and", "as", "at", "be", "by", "for", "from", "in", "is",
    "of", "on", "or", "the", "to", "was", "were", "with",
})


def _looks_like_continuation(previous: str, following: str) -> bool:
    """Reject OCR blank lines that split an obviously unfinished sentence."""
    if not previous or not following:
        return False
    if previous.rstrip().endswith((".", "!", "?", ";", ":")):
        return False
    first = following.lstrip()[:1]
    if first and first.islower():
        return True
    tail = re.findall(r"[A-Za-z]+", previous.casefold())
    return bool(tail and tail[-1] in _CONTINUATION_WORDS)


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


def _bbox(value):
    return tuple(float(x) for x in value) if value is not None else None


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
        midpoint = width // 2
        return [(0, 0, midpoint, height), (midpoint, 0, width, height)]
    return [whole]


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
        native_count = len("".join("".join(str(item[4]).split()) for item in raw_blocks))
        meaningful_tables = any(
            str(cell).strip() for rows, _ in detected_tables
            for row in rows for cell in row if cell is not None
        )
        if native_count <= 32 and not meaningful_tables and ocr_scanned:
            try:
                from PIL import Image
                import pytesseract
            except ImportError as exc:
                raise RuntimeError("scanned-page OCR requires the 'ocr' extra") from exc
            pix = page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            region_texts = [
                (
                    region,
                    _normalize_text_preserving_paragraphs(
                        pytesseract.image_to_string(image.crop(region))
                    ),
                )
                for region in _ocr_regions(image)
            ]
            ocr_count = sum(len("".join(text.split())) for _, text in region_texts)
            # Keep the existing textless-page fallback, even for a short OCR result.
            richer = ocr_count >= native_count + 32 and ocr_count >= 2 * native_count
            if ocr_count and (native_count == 0 or richer):
                for (x0, y0, x1, y1), text in region_texts:
                    if not text:
                        continue
                    counter += 1
                    blocks.append(TextBlock(
                        text=text,
                        block_id=f"text-{counter}",
                        kind="ocr_paragraph",
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
    doc.close()
    metadata["page_count"] = page_count
    return Document(source_id=source, title=title, blocks=tuple(blocks), metadata=metadata)
