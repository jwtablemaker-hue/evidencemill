from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiagramLabel:
    text: str
    label_id: str | None = None
    bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class DiagramCallout:
    callout: str
    label: str | None = None
    target_hint: str | None = None


@dataclass(frozen=True)
class LeaderRelation:
    source_label: str
    target_label: str
    confidence: float | None = None
