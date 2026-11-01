from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Iterable

from evidencemill.document import BBox, OcrWord


_CALLOUT_RE = re.compile(r"^(?:\d{1,3}|[A-Z]\d{0,3}|[A-Z]{1,3}\d{1,3})$")


@dataclass(frozen=True)
class DiagramLabel:
    text: str
    bbox: BBox
    confidence: float | None = None


@dataclass(frozen=True)
class DiagramCallout:
    callout: str
    bbox: BBox
    target_label: str | None = None
    distance: float | None = None


@dataclass(frozen=True)
class LeaderLine:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


def _center(bbox: BBox) -> tuple[float, float]:
    x0, y0, x1, y1 = bbox
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def recognize_callouts(words: Iterable[OcrWord]) -> tuple[DiagramCallout, ...]:
    out = []
    for word in words:
        text = word.text.strip()
        if _CALLOUT_RE.fullmatch(text):
            out.append(DiagramCallout(callout=text, bbox=word.bbox))
    return tuple(out)


def recognize_labels(words: Iterable[OcrWord]) -> tuple[DiagramLabel, ...]:
    out = []
    for word in words:
        text = word.text.strip()
        if text and not _CALLOUT_RE.fullmatch(text):
            out.append(DiagramLabel(text=text, bbox=word.bbox, confidence=word.confidence))
    return tuple(out)


def associate_callouts(words: Iterable[OcrWord], *, max_distance: float | None = None) -> tuple[DiagramCallout, ...]:
    word_list = tuple(words)
    callouts = recognize_callouts(word_list)
    labels = recognize_labels(word_list)
    resolved = []
    for callout in callouts:
        cx, cy = _center(callout.bbox)
        best = None
        best_distance = None
        for label in labels:
            lx, ly = _center(label.bbox)
            distance = math.hypot(lx - cx, ly - cy)
            if best_distance is None or distance < best_distance:
                best = label
                best_distance = distance
        if max_distance is not None and best_distance is not None and best_distance > max_distance:
            best = None
        resolved.append(DiagramCallout(
            callout=callout.callout,
            bbox=callout.bbox,
            target_label=best.text if best else None,
            distance=best_distance if best else None,
        ))
    return tuple(resolved)


def detect_leader_lines(image_path: str, *, min_length: int = 20) -> tuple[LeaderLine, ...]:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("leader-line detection requires the 'vision' extra") from exc

    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError(f"unable to read image: {image_path}")
    edges = cv2.Canny(image, 50, 150, apertureSize=3)
    found = cv2.HoughLinesP(
        edges,
        1,
        math.pi / 180,
        threshold=max(10, min_length // 2),
        minLineLength=min_length,
        maxLineGap=5,
    )
    if found is None:
        return ()
    lines = [
        LeaderLine(float(x1), float(y1), float(x2), float(y2))
        for row in found
        for x1, y1, x2, y2 in row
    ]
    return tuple(sorted(lines, key=lambda line: line.length, reverse=True))
