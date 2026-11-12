from __future__ import annotations

from pathlib import Path
import re
from statistics import median

from evidencemill.document import Document, FigureBlock, OcrWord, TableBlock, TextBlock
from evidencemill.illustration import associate_callouts
from evidencemill.ingest.image import ocr_words


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


def _looks_like_two_up_spread(image):
    """Recognize a two-page spread from this page alone.

    Keep the original strict blank-gutter detector for ordinary landscape
    pages. Very wide pages get one additional cheap layout check: both halves
    must contain meaningful visual structure, while a narrow vertical region
    near the midpoint must be substantially quieter than either half. This
    also works on dark/full-bleed pages where "blank" is black rather than white.
    """
    width, height = image.size
    if height <= 0 or width < 2.2 * height:
        return False

    from PIL import ImageStat

    sample = image.convert("L")
    sample.thumbnail((1100, 1100))
    sw, sh = sample.size
    top, bottom = int(sh * .05), int(sh * .95)
    if bottom <= top:
        return False

    left = ImageStat.Stat(
        sample.crop((int(sw * .03), top, int(sw * .47), bottom))
    ).stddev[0]
    right = ImageStat.Stat(
        sample.crop((int(sw * .53), top, int(sw * .97), bottom))
    ).stddev[0]
    side_activity = min(left, right)
    if side_activity < 8.0:
        return False

    window = max(4, int(sw * .008))
    half_window = max(2, window // 2)
    seam_activity = None
    for center in range(int(sw * .47), int(sw * .53) + 1, max(2, window // 3)):
        x0 = max(0, center - half_window)
        x1 = min(sw, center + half_window)
        if x1 <= x0:
            continue
        activity = ImageStat.Stat(
            sample.crop((x0, top, x1, bottom))
        ).stddev[0]
        seam_activity = activity if seam_activity is None else min(
            seam_activity, activity
        )

    return (
        seam_activity is not None
        and seam_activity <= 0.50 * side_activity
    )


def _mask_page_regions(image, bboxes, page_rect):
    """Mask structured table regions before prose OCR to avoid duplicate facts."""
    if not bboxes:
        return image
    from PIL import ImageDraw

    masked = image.copy()
    draw = ImageDraw.Draw(masked)
    page_width = max(float(page_rect.width), 1.0)
    page_height = max(float(page_rect.height), 1.0)
    sx = image.width / page_width
    sy = image.height / page_height
    px0 = float(page_rect.x0)
    py0 = float(page_rect.y0)
    for bbox in bboxes:
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        left = max(0, min(image.width, int((x0 - px0) * sx)))
        top = max(0, min(image.height, int((y0 - py0) * sy)))
        right = max(left, min(image.width, int((x1 - px0) * sx)))
        bottom = max(top, min(image.height, int((y1 - py0) * sy)))
        if right > left and bottom > top:
            draw.rectangle((left, top, right, bottom), fill="white")
    return masked


def _map_words_to_page(words, image_size, rect):
    """Map embedded-image OCR coordinates into the PDF page coordinate space."""
    width, height = image_size
    if width <= 0 or height <= 0 or rect is None:
        return ()
    sx = float(rect.width) / width
    sy = float(rect.height) / height
    mapped = []
    for word in words:
        x0, y0, x1, y1 = word.bbox
        mapped.append(OcrWord(
            text=word.text,
            bbox=(
                float(rect.x0) + x0 * sx,
                float(rect.y0) + y0 * sy,
                float(rect.x0) + x1 * sx,
                float(rect.y0) + y1 * sy,
            ),
            confidence=word.confidence,
        ))
    return tuple(mapped)


def _embedded_figure_labels(doc, page, xref, rect, pytesseract, Image, cache):
    """OCR a real embedded figure, but never duplicate a page-sized raster."""
    if rect is None:
        return ()
    page_area = max(float(page.rect.width * page.rect.height), 1.0)
    rect_area = max(float(rect.width * rect.height), 0.0)
    coverage = rect_area / page_area
    if coverage < 0.01 or coverage > 0.70 or rect.width < 40 or rect.height < 40:
        return ()

    cached = cache.get(xref)
    if cached is None:
        try:
            extracted = doc.extract_image(xref)
            payload = extracted.get("image")
            if not payload:
                cache[xref] = None
                return ()
            from io import BytesIO
            figure_image = Image.open(BytesIO(payload)).convert("RGB")
            words = ocr_words(figure_image, pytesseract)
            cached = (figure_image.size, words)
            cache[xref] = cached
        except Exception:
            cache[xref] = None
            return ()
    if cached is None:
        return ()
    image_size, words = cached
    return _map_words_to_page(words, image_size, rect)



def _longest_dark_run(gray, x: int, *, threshold: int = 235) -> tuple[int, int, int]:
    """Longest near-vertical dark run in one grayscale column."""
    values = gray.crop((x, 0, x + 1, gray.height)).tobytes()
    best_start = 0
    best_end = 0
    best_length = 0
    start = None
    for y, value in enumerate(values + b"\xff"):
        if value < threshold and start is None:
            start = y
        elif value >= threshold and start is not None:
            length = y - start
            if length > best_length:
                best_start = start
                best_end = y - 1
                best_length = length
            start = None
    return best_start, best_end, best_length


def _column_dark_fraction_and_std(
    gray,
    x: int,
    y0: int,
    y1: int,
    *,
    threshold: int = 245,
) -> tuple[float, float]:
    """Cheap grayscale column statistics without a numeric-array dependency."""
    histogram = gray.crop((x, y0, x + 1, y1)).histogram()
    count = max(1, sum(histogram))
    dark = sum(histogram[:threshold])
    mean = sum(value * amount for value, amount in enumerate(histogram)) / count
    variance = sum(
        ((value - mean) ** 2) * amount
        for value, amount in enumerate(histogram)
    ) / count
    return dark / count, variance ** 0.5


def _group_positions(values: list[int], *, gap: int = 2) -> list[tuple[int, int]]:
    if not values:
        return []
    groups: list[tuple[int, int]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value <= previous + gap:
            previous = value
            continue
        groups.append((start, previous))
        start = previous = value
    groups.append((start, previous))
    return groups


def _ruled_table_geometry(image):
    """Find a dense ruled table from parallel vertical rules only.

    This intentionally ignores generic column alignment. A region qualifies only
    when several long vertical rules establish a common table height and at
    least five stable separators survive a second pass inside those bounds.
    """
    gray = image.convert("L")
    gray.thumbnail((1100, 1100))
    width, height = gray.size
    if width < 100 or height < 100:
        return None

    strong: list[tuple[int, int, int, int]] = []
    for x in range(width):
        y0, y1, run = _longest_dark_run(gray, x)
        if run >= 0.25 * height:
            strong.append((x, y0, y1, run))

    rough_groups: list[list[tuple[int, int, int, int]]] = []
    for item in strong:
        if not rough_groups or item[0] > rough_groups[-1][-1][0] + 2:
            rough_groups.append([item])
        else:
            rough_groups[-1].append(item)

    max_rule_width = max(10, int(0.02 * width))
    rough = [
        max(group, key=lambda item: item[3])
        for group in rough_groups
        if group[-1][0] - group[0][0] + 1 <= max_rule_width
    ]
    if (
        len(rough) > 1
        and rough[0][0] <= 0.005 * width
        and rough[0][3] >= 0.90 * height
        and rough[1][0] <= 0.04 * width
    ):
        # A two-up page seam can sit immediately beside the true table border.
        rough = rough[1:]

    extent_rules = [item for item in rough if item[3] >= 0.40 * height]
    if len(extent_rules) < 4:
        return None
    table_y0 = min(item[1] for item in extent_rules)
    table_y1 = max(item[2] for item in extent_rules)
    if table_y1 - table_y0 < 0.20 * height:
        return None

    stable_x = []
    for x in range(width):
        dark_fraction, stddev = _column_dark_fraction_and_std(
            gray, x, table_y0, table_y1 + 1
        )
        if dark_fraction >= 0.90 and stddev <= 18.0:
            stable_x.append(x)

    separator_groups = [
        group
        for group in _group_positions(stable_x)
        if group[1] - group[0] + 1 <= max_rule_width
    ]
    separators = [(left + right) // 2 for left, right in separator_groups]
    if (
        len(separators) > 1
        and separators[0] <= 0.005 * width
        and separators[1] <= 0.04 * width
    ):
        separators = separators[1:]
    if len(separators) < 5:
        return None
    if separators[-1] - separators[0] < 0.35 * width:
        return None

    scale_x = image.width / width
    scale_y = image.height / height
    return (
        tuple(int(round(x * scale_x)) for x in separators),
        (
            int(round(table_y0 * scale_y)),
            int(round(table_y1 * scale_y)),
        ),
    )


def _drop_illustration_column(rows: list[list[str]]) -> list[list[str]]:
    """Discard a trailing blank-header image column when OCR yields only glyph noise."""
    if len(rows) < 2 or len(rows[0]) < 3 or rows[0][-1].strip():
        return rows
    values = [row[-1].strip() for row in rows[1:] if row[-1].strip()]
    if values and max(len(value) for value in values) <= 4:
        return [row[:-1] for row in rows]
    return rows


def _ocr_ruled_table(image, pytesseract):
    """Recover row/column structure from a strongly ruled raster table."""
    geometry = _ruled_table_geometry(image)
    if geometry is None:
        return None
    separators, (table_y0, table_y1) = geometry
    table_x0 = separators[0]
    table_x1 = separators[-1]
    if table_x1 <= table_x0 or table_y1 <= table_y0:
        return None

    crop = image.crop((table_x0, table_y0, table_x1 + 1, table_y1 + 1))
    data = pytesseract.image_to_data(
        crop,
        output_type=pytesseract.Output.DICT,
        config="--psm 6",
    )
    words = []
    for index, raw in enumerate(data.get("text", ())):
        text = str(raw).strip()
        if not text:
            continue
        words.append({
            "text": text,
            "left": int(data["left"][index]) + table_x0,
            "top": int(data["top"][index]) + table_y0,
            "width": int(data["width"][index]),
            "block": int(data["block_num"][index]),
            "par": int(data["par_num"][index]),
            "line": int(data["line_num"][index]),
        })
    if not words:
        return None

    grouped: dict[tuple[int, int, int], list[dict[str, object]]] = {}
    for word in words:
        key = (word["block"], word["par"], word["line"])
        grouped.setdefault(key, []).append(word)

    row_groups = sorted(
        grouped.values(),
        key=lambda group: min(int(word["top"]) for word in group),
    )
    rows: list[list[str]] = []
    for group in row_groups:
        cells = [""] * (len(separators) - 1)
        for word in sorted(group, key=lambda item: int(item["left"])):
            center = int(word["left"]) + int(word["width"]) / 2
            column = next(
                (
                    index
                    for index, (left, right) in enumerate(
                        zip(separators, separators[1:])
                    )
                    if left <= center <= right
                ),
                None,
            )
            if column is None:
                continue
            cells[column] = f"{cells[column]} {word['text']}".strip()
        if sum(bool(cell) for cell in cells) >= 2:
            rows.append(cells)

    if len(rows) < 3 or sum(bool(cell) for cell in rows[0]) < 3:
        return None
    rows = _drop_illustration_column(rows)
    rows[0] = [
        re.sub(r"^[\s_—–-]+(?=[A-Za-z])", "", cell).strip()
        for cell in rows[0]
    ]
    return rows, (table_x0, table_y0, table_x1, table_y1)


def _bbox_overlap_fraction(a, b) -> float:
    if a is None or b is None:
        return 0.0
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    smaller = min(
        max(0.0, (ax1 - ax0) * (ay1 - ay0)),
        max(0.0, (bx1 - bx0) * (by1 - by0)),
    )
    return intersection / smaller if smaller else 0.0


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
    two_up_ocr_pages = []
    ruled_table_ocr_pages = []
    figure_ocr_cache = {}

    for page_index, page in enumerate(doc):
        page_no = page_index + 1

        detected_tables: list[
            tuple[list[list[str | None]], tuple[float, float, float, float] | None]
        ] = []
        ocr_detected_tables: list[
            tuple[list[list[str]], tuple[float, float, float, float]]
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
        if (native_count <= 32 or corrupt_text) and ocr_scanned:
            try:
                from PIL import Image
                import pytesseract
            except ImportError as exc:
                raise RuntimeError("scanned-page OCR requires the 'ocr' extra") from exc
            pix = page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            regions = _ocr_regions(image)
            if len(regions) == 1 and _looks_like_two_up_spread(image):
                regions = _split_halves(image)
            if len(regions) == 2:
                two_up_ocr_pages.append(page_no)

            # Native table discovery cannot see tables embedded only in the page
            # raster. Recover only strongly ruled tables, before prose OCR, so
            # their row/column relationships survive and the same rectangle can
            # be masked out of the prose pass.
            for region in regions:
                rx0, ry0, rx1, ry1 = region
                recovered = _ocr_ruled_table(image.crop(region), pytesseract)
                if recovered is None:
                    continue
                rows, (tx0, ty0, tx1, ty1) = recovered
                pixel_bbox = (
                    rx0 + tx0,
                    ry0 + ty0,
                    rx0 + tx1,
                    ry0 + ty1,
                )
                table_bbox = (
                    pixel_bbox[0] * page.rect.width / pix.width,
                    pixel_bbox[1] * page.rect.height / pix.height,
                    pixel_bbox[2] * page.rect.width / pix.width,
                    pixel_bbox[3] * page.rect.height / pix.height,
                )
                if any(
                    _bbox_overlap_fraction(table_bbox, native_bbox) >= 0.50
                    for _, native_bbox in detected_tables
                    if native_bbox is not None
                ):
                    continue
                ocr_detected_tables.append((rows, table_bbox))
            if ocr_detected_tables:
                ruled_table_ocr_pages.append(page_no)

            # Structured tables have already been extracted. Mask those exact
            # rectangles so OCR can recover the rest of the page without
            # re-emitting table cells as prose.
            prose_image = _mask_page_regions(
                image,
                [
                    bbox
                    for _, bbox in [*detected_tables, *ocr_detected_tables]
                    if bbox is not None
                ],
                page.rect,
            )
            region_texts = [
                (
                    region,
                    _normalize_text_preserving_paragraphs(
                        _ocr_text_with_layout(prose_image.crop(region), pytesseract)
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

        table_bboxes = [
            bbox
            for _, bbox in [*detected_tables, *ocr_detected_tables]
            if bbox is not None
        ]
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

        for rows, table_bbox in ocr_detected_tables:
            counter += 1
            blocks.append(TableBlock(
                rows=tuple(tuple(str(cell).strip() for cell in row) for row in rows),
                block_id=f"table-{counter}",
                page=page_no,
                bbox=table_bbox,
                header_rows=1,
                row_header_columns=1,
                layout="matrix",
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
                labels = ()
                callouts = ()
                if ocr_scanned and rect is not None:
                    try:
                        from PIL import Image
                        import pytesseract
                    except ImportError:
                        Image = None
                        pytesseract = None
                    if Image is not None and pytesseract is not None:
                        labels = _embedded_figure_labels(
                            doc, page, xref, rect, pytesseract, Image, figure_ocr_cache
                        )
                        if labels:
                            callouts = tuple(
                                item.callout for item in associate_callouts(labels)
                            )
                counter += 1
                blocks.append(FigureBlock(
                    block_id=f"figure-{counter}",
                    page=page_no,
                    bbox=_bbox(rect),
                    labels=labels,
                    callouts=callouts,
                    source_path=f"{p}#page={page_no}&xref={xref}",
                ))

    metadata = dict(doc.metadata or {})
    title = metadata.get("title") or None
    page_count = doc.page_count
    if two_up_ocr_pages:
        metadata["ocr_two_up_pages"] = list(dict.fromkeys(two_up_ocr_pages))
    if ruled_table_ocr_pages:
        metadata["ocr_ruled_table_pages"] = list(dict.fromkeys(ruled_table_ocr_pages))
    doc.close()
    metadata["page_count"] = page_count
    return Document(source_id=source, title=title, blocks=tuple(blocks), metadata=metadata)
