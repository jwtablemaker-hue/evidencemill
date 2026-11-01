from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    location: str | None = None
    raw_text: str | None = None


@dataclass(frozen=True)
class EvidenceObservation:
    """Neutral extracted structure, not a canonical fact."""

    kind: str
    source: SourceRef
    value: Any = None
    unit: str | None = None
    subject_hint: str | None = None
    property_hint: str | None = None
    qualifiers: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)
    ambiguous: bool = False
