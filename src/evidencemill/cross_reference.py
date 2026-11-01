from __future__ import annotations

from dataclasses import dataclass
import re

from evidencemill.document import Document, FigureBlock, TableBlock, TextBlock


_REF_RE = re.compile(
    r"\b(?P<kind>fig(?:ure)?|table|section|sec\.?|appendix)\s*"
    r"(?P<label>[A-Za-z]?\d+(?:[.-]\d+)*|[A-Za-z])\b",
    re.I,
)
_LABEL_RE = re.compile(
    r"^\s*(?P<kind>fig(?:ure)?|table|section|sec\.?|appendix)\s*"
    r"(?P<label>[A-Za-z]?\d+(?:[.-]\d+)*|[A-Za-z])\b",
    re.I,
)


@dataclass(frozen=True)
class CrossReference:
    source_block_id: str
    kind: str
    label: str
    target_block_id: str | None
    text: str


def _norm_kind(kind: str) -> str:
    value = kind.casefold().rstrip(".")
    if value.startswith("fig"):
        return "figure"
    if value.startswith("sec"):
        return "section"
    return value


def _index(document: Document) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for block in document.blocks:
        candidates: list[str] = []
        if isinstance(block, FigureBlock) and block.caption:
            candidates.append(block.caption)
        elif isinstance(block, TableBlock) and block.caption:
            candidates.append(block.caption)
        elif isinstance(block, TextBlock) and block.kind == "heading":
            candidates.append(block.text)
        for value in candidates:
            match = _LABEL_RE.match(value)
            if match:
                result[(_norm_kind(match.group("kind")), match.group("label").casefold())] = block.block_id
    return result


def resolve_cross_references(document: Document) -> tuple[CrossReference, ...]:
    index = _index(document)
    refs: list[CrossReference] = []
    for block in document.blocks:
        if not isinstance(block, TextBlock):
            continue
        for match in _REF_RE.finditer(block.text):
            kind = _norm_kind(match.group("kind"))
            label = match.group("label")
            refs.append(CrossReference(
                source_block_id=block.block_id,
                kind=kind,
                label=label,
                target_block_id=index.get((kind, label.casefold())),
                text=match.group(0),
            ))
    return tuple(refs)
