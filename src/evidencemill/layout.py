from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutBlock:
    kind: str
    text: str | None = None
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    parent_id: str | None = None
    block_id: str | None = None


@dataclass(frozen=True)
class HeadingScope:
    heading: str
    block_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaptionLink:
    caption_block_id: str
    target_block_id: str
