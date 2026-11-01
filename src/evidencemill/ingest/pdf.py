from __future__ import annotations

from pathlib import Path

from evidencemill.document import Document, FigureBlock, TableBlock, TextBlock


def _bbox(value):
    return tuple(float(x) for x in value) if value is not None else None


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
        raw_blocks = page.get_text("blocks", sort=True)
        if not raw_blocks and ocr_scanned:
            try:
                from PIL import Image
                import pytesseract
            except ImportError as exc:
                raise RuntimeError("scanned-page OCR requires the 'ocr' extra") from exc
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            ocr_text = " ".join(pytesseract.image_to_string(image).split()).strip()
            if ocr_text:
                counter += 1
                blocks.append(TextBlock(text=ocr_text, block_id=f"text-{counter}", kind="ocr_paragraph", page=page_no, bbox=(0.0, 0.0, float(page.rect.width), float(page.rect.height))))
        for item in raw_blocks:
            x0, y0, x1, y1, text, *_ = item
            text = " ".join(str(text).split()).strip()
            if not text:
                continue
            counter += 1
            blocks.append(TextBlock(text=text, block_id=f"text-{counter}", kind="paragraph", page=page_no, bbox=(float(x0), float(y0), float(x1), float(y1))))

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
                counter += 1
                blocks.append(TableBlock(rows=tuple(tuple("" if cell is None else str(cell).strip() for cell in row) for row in rows), block_id=f"table-{counter}", page=page_no, bbox=_bbox(getattr(table, "bbox", None))))

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
                blocks.append(FigureBlock(block_id=f"figure-{counter}", page=page_no, bbox=_bbox(rect), source_path=f"{p}#page={page_no}&xref={xref}"))

    metadata = dict(doc.metadata or {})
    title = metadata.get("title") or None
    page_count = doc.page_count
    doc.close()
    metadata["page_count"] = page_count
    return Document(source_id=source, title=title, blocks=tuple(blocks), metadata=metadata)
