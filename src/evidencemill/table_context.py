from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from .models import EvidenceObservation, SourceRef


_UNIT_HEADER_RE = re.compile(
    r"^(?P<label>.*?)\s*(?:\((?P<paren>[^)]+)\)|\[(?P<bracket>[^]]+)\])\s*$"
)

_HEADER_WORDS = {
    "item", "items", "model", "models", "variant", "variants", "version",
    "parameter", "parameters", "property", "properties", "specification",
    "specifications", "spec", "specs", "value", "values", "description",
    "unit", "units", "name", "feature", "features", "option", "options",
    "rated", "nominal", "maximum", "minimum", "power", "voltage", "current",
    "capacity", "energy", "speed", "range", "weight", "mass", "length",
    "width", "height", "temperature", "pressure", "torque",
}


@dataclass(frozen=True)
class TableCellContext:
    row_index: int
    column_index: int
    row_header: str | None
    column_header: str | None
    value: str
    inherited_unit: str | None = None
    section_heading: str | None = None
    table_layout: str = "matrix"
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


def _normalize_rows(rows: Sequence[Sequence[object]]) -> list[list[str]]:
    width = max((len(row) for row in rows), default=0)
    return [
        ["" if i >= len(row) or row[i] is None else str(row[i]).strip() for i in range(width)]
        for row in rows
    ]


def _headerish(text: str) -> bool:
    words = {
        re.sub(r"[^a-z0-9]+", "", part.casefold())
        for part in re.split(r"\s+", text.strip())
        if part.strip()
    }
    return bool(words & _HEADER_WORDS)


def infer_table_layout(rows: Sequence[Sequence[object]]) -> tuple[str, int]:
    """Infer only the broad table shape needed for context binding."""
    normalized = _normalize_rows(rows)
    if not normalized:
        return "matrix", 0

    width = len(normalized[0])
    if width != 2:
        return "matrix", 1

    nonempty = [row for row in normalized if any(row)]
    if not nonempty:
        return "matrix", 0

    first = nonempty[0]
    if first[0] and not first[1]:
        return "key_value", 0

    if _headerish(first[0]) and _headerish(first[1]):
        return "matrix", 1

    paired = [row for row in nonempty if row[0] and row[1]]
    if len(paired) >= 2:
        return "key_value", 0

    return "matrix", 1


def parse_table(
    rows: Sequence[Sequence[object]],
    *,
    source_id: str,
    header_rows: int | None = 1,
    row_header_columns: int = 1,
    location: str | None = None,
    layout: str = "auto",
    table_subject: str | None = None,
) -> list[EvidenceObservation]:
    """Convert a table into explicit cell-context observations.

    Matrix layout binds cells to row and column headers.
    Key-value layout treats the left cell as a property label and the right cell
    as its value. Empty-value rows become local section headings.
    Auto selects between those shapes without assigning domain meaning.
    """
    if row_header_columns < 0:
        raise ValueError("row_header_columns cannot be negative")
    if layout not in {"auto", "matrix", "key_value"}:
        raise ValueError("layout must be auto, matrix or key_value")

    normalized = _normalize_rows(rows)
    if not normalized:
        return []

    if layout == "auto":
        inferred_layout, inferred_headers = infer_table_layout(normalized)
        layout = inferred_layout
        if header_rows is None:
            header_rows = inferred_headers

    if header_rows is None:
        header_rows = 0 if layout == "key_value" else 1
    if header_rows < 0:
        raise ValueError("header_rows cannot be negative")

    width = len(normalized[0])
    if width == 0:
        return []

    if layout == "key_value":
        if width < 2:
            return []
        out: list[EvidenceObservation] = []
        section_heading: str | None = None
        value_column = max(1, row_header_columns)

        for row_index, row in enumerate(normalized):
            property_parts = [
                row[c] for c in range(min(row_header_columns, width)) if row[c]
            ]
            property_text = " / ".join(property_parts).strip()
            value = row[value_column] if value_column < width else ""

            if property_text and not value:
                section_heading = property_text
                continue
            if not property_text or not value:
                continue

            property_label, inherited_unit = split_header_unit(property_text)
            context = TableCellContext(
                row_index=row_index,
                column_index=value_column,
                row_header=property_label or None,
                column_header=None,
                value=value,
                inherited_unit=inherited_unit,
                section_heading=section_heading,
                table_layout="key_value",
            )
            raw_text = f"{property_text}: {value}"
            out.append(EvidenceObservation(
                kind="table_cell",
                source=SourceRef(
                    source_id=source_id,
                    location=f"{location + ':' if location else ''}r{row_index + 1}c{value_column + 1}",
                    raw_text=raw_text,
                ),
                value=value,
                unit=inherited_unit,
                subject_hint=table_subject,
                property_hint=property_label or None,
                context={
                    "row_index": context.row_index,
                    "column_index": context.column_index,
                    "row_header": context.row_header,
                    "column_header": None,
                    "section_heading": section_heading,
                    "table_subject": table_subject,
                    "table_layout": "key_value",
                },
                ambiguous=not bool(property_label),
            ))
        return out

    if len(normalized) <= header_rows:
        return []

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
                table_layout="matrix",
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
                    "table_subject": table_subject,
                    "table_layout": "matrix",
                },
                ambiguous=not bool(row_header or column_header),
            ))
    return out
