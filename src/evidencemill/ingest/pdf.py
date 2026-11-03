from __future__ import annotations

from pathlib import Path
import re

from evidencemill.document import Document, FigureBlock, TableBlock, TextBlock


def _bbox(value):
    return tuple(float(x) for x in value) if value is not None else None


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
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            ocr_text = " ".join(pytesseract.image_to_string(image).split()).strip()
            ocr_count = len("".join(ocr_text.split()))
            # Keep the existing textless-page fallback, even for a short OCR result.
            richer = ocr_count >= native_count + 32 and ocr_count >= 2 * native_count
            if ocr_text and (native_count == 0 or richer):
                counter += 1
                blocks.append(TextBlock(
                    text=ocr_text,
                    block_id=f"text-{counter}",
                    kind="ocr_paragraph",
                    page=page_no,
                    bbox=(0.0, 0.0, float(page.rect.width), float(page.rect.height)),
                ))
                # OCR is primary. Retain native lines absent from it, without
                # emitting a second copy of lines OCR already reproduced.
                remaining = []
                for item in raw_blocks:
                    missing = []
                    for line in str(item[4]).splitlines():
                        line = " ".join(line.split())
                        if line and not re.search(
                            r"(?<!\w)" + re.escape(line) + r"(?!\w)",
                            ocr_text, flags=re.IGNORECASE,
                        ):
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
            text = " ".join(str(text).split()).strip()
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
