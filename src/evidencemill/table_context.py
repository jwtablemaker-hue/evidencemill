from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from .models import EvidenceObservation, SourceRef


_UNIT_HEADER_RE = re.compile(
    r"^(?P<label>.*?)\s*(?:\((?P<paren>[^)]+)\)|\[(?P<bracket>[^]]+)\])\s*$"
)


@dataclass(frozen=True)
class TableCellContext:
    row_index: int
    column_index: int
    row_header: str | None
    column_header: str | None
    value: str
    inherited_unit: str | None = None
    notes: tuple[str, ...] = ()


def split_header_unit(header: str) -> tuple[str, str | None]:
    text = str(header or "").strip()
    match = _UNIT_HEADER_RE.match(text)
    if not match:
        return text, None
    unit = (match.group("paren") or match.group("bracket") or "").strip()
    label = match.group("label").strip()
    if not unit:
        return text, None
    return label, unit


def parse_table(
    rows: Sequence[Sequence[object]],
    *,
    source_id: str,
    header_rows: int = 1,
    row_header_columns: int = 1,
    location: str | None = None,
) -> list[EvidenceObservation]:
    """Convert a rectangular table into explicit cell-context observations.

    This does not guess domain meaning. It only binds each non-header cell to
    the visible row/column context that makes the cell interpretable.
    """
    if header_rows < 1:
        raise ValueError("header_rows must be at least 1")
    if row_header_columns < 0:
        raise ValueError("row_header_columns cannot be negative")
    if len(rows) <= header_rows:
        return []

    width = max((len(row) for row in rows), default=0)
    normalized = [
        ["" if i >= len(row) or row[i] is None else str(row[i]).strip() for i in range(width)]
        for row in rows
    ]

    column_headers: list[str | None] = [None] * width
    column_units: list[str | None] = [None] * width
    for col in range(width):
        pieces = [normalized[r][col] for r in range(header_rows) if normalized[r][col]]
        if pieces:
            label, unit = split_header_unit(" / ".join(pieces))
            column_headers[col] = label or None
            column_units[col] = unit

    out: list[EvidenceObservation] = []
    for row_index in range(header_rows, len(normalized)):
        row = normalized[row_index]
        row_header_parts = [row[c] for c in range(min(row_header_columns, width)) if row[c]]
        row_header = " / ".join(row_header_parts) or None

        for col in range(row_header_columns, width):
            value = row[col]
            if not value:
                continue
            column_header = column_headers[col]
            unit = column_units[col]
            context = TableCellContext(
                row_index=row_index,
                column_index=col,
                row_header=row_header,
                column_header=column_header,
                value=value,
                inherited_unit=unit,
            )
            out.append(EvidenceObservation(
                kind="table_cell",
                source=SourceRef(
                    source_id=source_id,
                    location=f"{location + ':' if location else ''}r{row_index + 1}c{col + 1}",
                    raw_text=value,
                ),
                value=value,
                unit=unit,
                subject_hint=row_header,
                property_hint=column_header,
                context={
                    "row_index": context.row_index,
                    "column_index": context.column_index,
                    "row_header": context.row_header,
                    "column_header": context.column_header,
                },
                ambiguous=not bool(row_header or column_header),
            ))
    return out
