from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class OcrWord:
    text: str
    bbox: BBox
    confidence: float | None = None


@dataclass(frozen=True)
class TextBlock:
    text: str
    block_id: str
    kind: str = "paragraph"
    page: int | None = None
    bbox: BBox | None = None
    heading_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class TableBlock:
    rows: tuple[tuple[str, ...], ...]
    block_id: str
    caption: str | None = None
    page: int | None = None
    bbox: BBox | None = None
    heading_path: tuple[str, ...] = ()
    header_rows: int | None = None
    row_header_columns: int = 1
    layout: str = "auto"
    subject_hint: str | None = None


@dataclass(frozen=True)
class FigureBlock:
    block_id: str
    caption: str | None = None
    page: int | None = None
    bbox: BBox | None = None
    heading_path: tuple[str, ...] = ()
    labels: tuple[OcrWord, ...] = ()
    callouts: tuple[str, ...] = ()
    source_path: str | None = None


DocumentBlock = TextBlock | TableBlock | FigureBlock


@dataclass(frozen=True)
class Document:
    source_id: str
    blocks: tuple[DocumentBlock, ...]
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
