from __future__ import annotations

from pathlib import Path

from evidencemill.document import Document, FigureBlock, OcrWord
from evidencemill.illustration import associate_callouts


def parse_image(path: str | Path, *, source_id: str | None = None, language: str = "eng") -> Document:
    try:
        from PIL import Image
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise RuntimeError("image OCR requires the 'ocr' extra") from exc

    p = Path(path)
    image = Image.open(p)
    data = pytesseract.image_to_data(image, lang=language, output_type=Output.DICT)
    words: list[OcrWord] = []
    count = len(data.get("text", []))
    for i in range(count):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        x = float(data["left"][i]); y = float(data["top"][i]); w = float(data["width"][i]); h = float(data["height"][i])
        raw_conf = data.get("conf", [None] * count)[i]
        try:
            confidence = float(raw_conf)
        except (TypeError, ValueError):
            confidence = None
        words.append(OcrWord(text=text, bbox=(x, y, x + w, y + h), confidence=confidence))

    associations = associate_callouts(words)
    figure = FigureBlock(block_id="figure-1", labels=tuple(words), callouts=tuple(item.callout for item in associations), source_path=str(p))
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
