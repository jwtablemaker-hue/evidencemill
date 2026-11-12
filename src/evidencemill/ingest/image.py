from __future__ import annotations

from pathlib import Path

from evidencemill.document import Document, FigureBlock, OcrWord
from evidencemill.illustration import associate_callouts


def ocr_words(image, pytesseract, *, language: str = "eng") -> tuple[OcrWord, ...]:
    """Return positioned OCR words for image/figure structure reuse."""
    data = pytesseract.image_to_data(
        image,
        lang=language,
        output_type=pytesseract.Output.DICT,
    )
    words: list[OcrWord] = []
    count = len(data.get("text", []))
    for i in range(count):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        x = float(data["left"][i])
        y = float(data["top"][i])
        w = float(data["width"][i])
        h = float(data["height"][i])
        raw_conf = data.get("conf", [None] * count)[i]
        try:
            confidence = float(raw_conf)
        except (TypeError, ValueError):
            confidence = None
        words.append(OcrWord(
            text=text,
            bbox=(x, y, x + w, y + h),
            confidence=confidence,
        ))
    return tuple(words)


def parse_image(path: str | Path, *, source_id: str | None = None, language: str = "eng") -> Document:
    try:
        from PIL import Image
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("image OCR requires the 'ocr' extra") from exc

    p = Path(path)
    image = Image.open(p)
    words = ocr_words(image, pytesseract, language=language)

    associations = associate_callouts(words)
    figure = FigureBlock(block_id="figure-1", labels=words, callouts=tuple(item.callout for item in associations), source_path=str(p))
    return Document(
        source_id=source_id or p.name,
        blocks=(figure,),
        metadata={
            "image_size": image.size,
            "callout_associations": [
                {"callout": item.callout, "target_label": item.target_label, "distance": item.distance}
                for item in associations
            ],
        },
    )
