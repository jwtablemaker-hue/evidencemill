from __future__ import annotations

from pathlib import Path
import re

from evidencemill.cross_reference import resolve_cross_references
from evidencemill.document import Document, FigureBlock, TableBlock, TextBlock
from evidencemill.illustration import associate_callouts
from evidencemill.models import EvidenceObservation, SourceRef
from evidencemill.sentence_structure import analyze_statement, requires_scoped_review
from evidencemill.table_context import parse_table


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def split_sentences(text: str) -> tuple[str, ...]:
    parts = tuple(part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip())
    return parts or ((text.strip(),) if text.strip() else ())


def _location(block, suffix: str | None = None) -> str:
    parts = []
    if getattr(block, "page", None) is not None:
        parts.append(f"page-{block.page}")
    parts.append(block.block_id)
    if suffix:
        parts.append(suffix)
    return ":".join(parts)


def _text_observations(document: Document, block: TextBlock) -> list[EvidenceObservation]:
    out = []
    if block.kind == "heading":
        out.append(EvidenceObservation(kind="heading", source=SourceRef(document.source_id, _location(block), block.text), value=block.text, context={"heading_path": list(block.heading_path)}))
        return out
    for index, sentence in enumerate(split_sentences(block.text), start=1):
        structure = analyze_statement(sentence)
        out.append(EvidenceObservation(
            kind="statement",
            source=SourceRef(document.source_id, _location(block, f"s{index}"), sentence),
            value=sentence,
            qualifiers=tuple(sorted(structure.flags)),
            context={"block_id": block.block_id, "heading_path": list(block.heading_path), "structure": structure.to_dict()},
            ambiguous=requires_scoped_review(structure),
        ))
        for measurement_index, measurement in enumerate(structure.measurements, start=1):
            out.append(EvidenceObservation(
                kind="measurement",
                source=SourceRef(
                    document.source_id,
                    _location(block, f"s{index}:m{measurement_index}"),
                    sentence,
                ),
                value=measurement.value,
                unit=measurement.unit,
                subject_hint=measurement.component_kind or cell.subject_hint,
                property_hint=cell.property_hint,
                qualifiers=measurement.qualifiers,
                context={"scope": measurement.scope, "placement": measurement.placement, "multiplicity": measurement.multiplicity, "value_kind": measurement.value_kind, "tolerance": measurement.tolerance, "comparison": measurement.comparison, "local_label": measurement.local_label, "measurement_text": measurement.text, "statement": sentence, "heading_path": list(block.heading_path)},
                ambiguous=(
                    measurement.scope == "unknown"
                    and not cell.property_hint
                ),
            ))
    return out


def _table_observations(document: Document, block: TableBlock) -> list[EvidenceObservation]:
    cells = parse_table(
        block.rows,
        source_id=document.source_id,
        header_rows=block.header_rows,
        row_header_columns=block.row_header_columns,
        location=_location(block),
        layout=block.layout,
        table_subject=block.subject_hint,
    )
    out: list[EvidenceObservation] = list(cells)

    for cell in cells:
        context = dict(cell.context)
        labels = [
            context.get("section_heading"),
            cell.property_hint,
            cell.subject_hint,
        ]
        label_text = " ".join(
            str(item).strip()
            for item in labels
            if item and str(item).strip()
        )
        value_text = str(cell.value).strip()
        statement = f"{label_text}: {value_text}" if label_text else value_text

        structure = analyze_statement(statement)
        if not structure.measurements and cell.unit:
            structure = analyze_statement(f"{statement} {cell.unit}")

        for measurement_index, measurement in enumerate(structure.measurements, start=1):
            out.append(EvidenceObservation(
                kind="measurement",
                source=SourceRef(
                    document.source_id,
                    f"{cell.source.location}:m{measurement_index}",
                    cell.source.raw_text or statement,
                ),
                value=measurement.value,
                unit=measurement.unit,
                subject_hint=measurement.component_kind,
                qualifiers=measurement.qualifiers,
                context={
                    "scope": measurement.scope,
                    "placement": measurement.placement,
                    "multiplicity": measurement.multiplicity,
                    "value_kind": measurement.value_kind,
                    "tolerance": measurement.tolerance,
                    "comparison": measurement.comparison,
                    "local_label": measurement.local_label,
                    "measurement_text": measurement.text,
                    "statement": statement,
                    "heading_path": list(block.heading_path),
                    "table_property": cell.property_hint,
                    "table_subject": cell.subject_hint,
                    "table_section": context.get("section_heading"),
                    "table_layout": context.get("table_layout"),
                    "table_cell_location": cell.source.location,
                },
                ambiguous=measurement.scope == "unknown",
            ))
    return out


def _figure_observations(document: Document, block: FigureBlock) -> list[EvidenceObservation]:
    out = []
    if block.caption:
        out.append(EvidenceObservation(kind="figure_caption", source=SourceRef(document.source_id, _location(block, "caption"), block.caption), value=block.caption, context={"heading_path": list(block.heading_path)}))
    associations = associate_callouts(block.labels) if block.labels else ()
    association_by_callout = {item.callout: item for item in associations}
    for index, word in enumerate(block.labels, start=1):
        out.append(EvidenceObservation(kind="figure_label", source=SourceRef(document.source_id, _location(block, f"label-{index}"), word.text), value=word.text, context={"bbox": list(word.bbox), "confidence": word.confidence}))
    for callout in block.callouts:
        relation = association_by_callout.get(callout)
        out.append(EvidenceObservation(kind="figure_callout", source=SourceRef(document.source_id, _location(block, f"callout-{callout}"), callout), value=callout, subject_hint=relation.target_label if relation else None, context={"distance": relation.distance if relation else None}, ambiguous=relation is None or relation.target_label is None))
    return out


def process_document(document: Document) -> list[EvidenceObservation]:
    observations: list[EvidenceObservation] = []
    for block in document.blocks:
        if isinstance(block, TextBlock):
            observations.extend(_text_observations(document, block))
        elif isinstance(block, TableBlock):
            observations.extend(_table_observations(document, block))
        elif isinstance(block, FigureBlock):
            observations.extend(_figure_observations(document, block))
    for ref in resolve_cross_references(document):
        observations.append(EvidenceObservation(kind="cross_reference", source=SourceRef(document.source_id, ref.source_block_id, ref.text), value=ref.label, property_hint=ref.kind, context={"target_block_id": ref.target_block_id}, ambiguous=ref.target_block_id is None))
    return observations


def ingest_path(path: str | Path, *, source_id: str | None = None, ocr: bool = False) -> Document:
    p = Path(path)
    suffix = p.suffix.casefold()
    source = source_id or p.name
    if suffix in {".txt", ".md", ".rst"}:
        from evidencemill.ingest.text import parse_text
        return parse_text(p.read_text(encoding="utf-8", errors="replace"), source_id=source)
    if suffix in {".html", ".htm"}:
        from evidencemill.ingest.html import parse_html_file
        return parse_html_file(p, source_id=source)
    if suffix in {".csv", ".tsv"}:
        from evidencemill.ingest.csv import parse_csv
        kwargs = {"delimiter": "\t"} if suffix == ".tsv" else {}
        return parse_csv(p, source_id=source, **kwargs)
    if suffix == ".pdf":
        from evidencemill.ingest.pdf import parse_pdf
        return parse_pdf(p, source_id=source, ocr_scanned=ocr)
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
        from evidencemill.ingest.image import parse_image
        return parse_image(p, source_id=source)
    raise ValueError(f"unsupported input type: {suffix or '<none>'}")
