from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re

from evidencemill.cross_reference import resolve_cross_references
from evidencemill.document import Document, FigureBlock, TableBlock, TextBlock
from evidencemill.illustration import associate_callouts
from evidencemill.models import EvidenceObservation, SourceRef
from evidencemill.sentence_structure import _tokens, analyze_statement, requires_scoped_review
from evidencemill.table_context import parse_table


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def split_sentences(text: str) -> tuple[str, ...]:
    parts = []
    for paragraph in re.split(r"\n\s*\n+", text):
        paragraph = " ".join(paragraph.split()).strip()
        if not paragraph:
            continue
        parts.extend(
            part.strip()
            for part in _SENTENCE_SPLIT.split(paragraph)
            if part.strip()
        )
    return tuple(parts) or ((text.strip(),) if text.strip() else ())


def _location(block, suffix: str | None = None) -> str:
    parts = []
    if getattr(block, "page", None) is not None:
        parts.append(f"page-{block.page}")
    parts.append(block.block_id)
    if suffix:
        parts.append(suffix)
    return ":".join(parts)


def _sentence_structural_references(sentence: str, refs) -> list[dict[str, object]]:
    """Attach only explicit table/figure/section references to parsed prose."""
    folded = sentence.casefold()
    out = []
    for ref in refs:
        if ref.text.casefold() not in folded:
            continue
        out.append({
            "kind": ref.kind,
            "label": ref.label,
            "target_block_id": ref.target_block_id,
            "source_text": ref.text,
        })
    return out


def _text_observations(
    document: Document,
    block: TextBlock,
    *,
    structural_refs=(),
) -> list[EvidenceObservation]:
    out = []
    if block.kind == "ocr_layout_review":
        # The recovered region can cross columns. Retain its text and location
        # together until reading order can be checked against the source page.
        return [EvidenceObservation(
            kind="statement", source=SourceRef(document.source_id, _location(block), block.text),
            value=block.text, ambiguous=True,
            context={"block_id": block.block_id, "bbox": block.bbox, "ocr_layout_review": True},
        )]
    if block.kind == "heading":
        out.append(EvidenceObservation(kind="heading", source=SourceRef(document.source_id, _location(block), block.text), value=block.text, context={"heading_path": list(block.heading_path)}))
        return out
    for index, sentence in enumerate(split_sentences(block.text), start=1):
        references = _sentence_structural_references(sentence, structural_refs)
        structure = analyze_statement(sentence)
        statement_context = {
            "block_id": block.block_id,
            "heading_path": list(block.heading_path),
            "structure": structure.to_dict(),
        }
        if references:
            statement_context["structural_references"] = references
        out.append(EvidenceObservation(
            kind="statement",
            source=SourceRef(document.source_id, _location(block, f"s{index}"), sentence),
            value=sentence,
            qualifiers=tuple(sorted(structure.flags)),
            context=statement_context,
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
                subject_hint=measurement.component_kind,
                property_hint=measurement.local_label,
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
                    "statement": sentence,
                    "statement_structure": structure.to_dict(),
                    "heading_path": list(block.heading_path),
                    **({"structural_references": references} if references else {}),
                },
                ambiguous=(
                    measurement.scope == "unknown"
                ),
            ))
    return out


def _parallel_table_alternatives(
    value_header: object,
    value_text: str,
) -> tuple[tuple[str, str], ...]:
    """Preserve positional alternatives without asserting semantic equivalence.

    Only spaced slash separators qualify. This avoids splitting units such as
    km/h and leaves compact expressions such as 100-120V/200-240V untouched.
    """
    header = str(value_header or "").strip()
    if not header:
        return ()
    header_parts = tuple(
        part.strip() for part in re.split(r"\s+/\s+", header)
        if part.strip()
    )
    value_parts = tuple(
        part.strip() for part in re.split(r"\s+/\s+", value_text)
        if part.strip()
    )
    if len(header_parts) < 2 or len(header_parts) != len(value_parts):
        return ()
    if any(len(analyze_statement(part).measurements) != 1 for part in value_parts):
        return ()
    return tuple(zip(header_parts, value_parts))


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

        # Labels supply semantic context, but only numbers originating in this
        # value cell may become its measurements. Numeric model/spec headers
        # remain in the original statement and cell context as source evidence.
        value_start = len(label_text) + 2 if label_text else 0
        structure = analyze_statement(statement)
        tokens = _tokens(statement)
        measurements = tuple(
            item for item in structure.measurements
            if tokens[item.token_index].start >= value_start
        )
        if not measurements and cell.unit:
            unit_statement = f"{statement} {cell.unit}"
            structure = analyze_statement(unit_statement)
            tokens = _tokens(unit_statement)
            measurements = tuple(
                item for item in structure.measurements
                if tokens[item.token_index].start >= value_start
            )

        structure = replace(structure, measurements=measurements)
        parallel = _parallel_table_alternatives(
            context.get("value_column_header"),
            value_text,
        )
        for measurement_index, measurement in enumerate(measurements, start=1):
            measurement_context = {
                "scope": measurement.scope,
                "placement": measurement.placement,
                "multiplicity": measurement.multiplicity,
                "value_kind": measurement.value_kind,
                "tolerance": measurement.tolerance,
                "comparison": measurement.comparison,
                "local_label": measurement.local_label,
                "measurement_text": measurement.text,
                "statement": statement,
                "statement_structure": structure.to_dict(),
                "heading_path": list(block.heading_path),
                "table_property": cell.property_hint,
                "table_subject": cell.subject_hint,
                "table_section": context.get("section_heading"),
                "table_layout": context.get("table_layout"),
                "table_value_header": context.get("value_column_header"),
                "table_cell_location": cell.source.location,
                "source_caveats": context.get("source_caveats", []),
            }
            if parallel and len(parallel) == len(measurements):
                header_part, value_part = parallel[measurement_index - 1]
                measurement_context.update({
                    "table_parallel_header_part": header_part,
                    "table_parallel_value_part": value_part,
                    "table_parallel_position": measurement_index,
                    "table_parallel_count": len(parallel),
                    "table_parallel_alignment": "positional_candidate",
                })
            out.append(EvidenceObservation(
                kind="measurement",
                source=SourceRef(
                    document.source_id,
                    f"{cell.source.location}:m{measurement_index}",
                    cell.source.raw_text or statement,
                ),
                value=measurement.value,
                unit=measurement.unit,
                subject_hint=measurement.component_kind or cell.subject_hint,
                qualifiers=measurement.qualifiers,
                context=measurement_context,
                ambiguous=(measurement.scope == "unknown" and not cell.property_hint),
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


def _model_list(text: str) -> list[str]:
    """Parse explicit model enumerations without requiring similar model names."""
    parts = re.split(r"\s*(?:/|,|\band\b|&)\s*", text, flags=re.I)
    if len(parts) < 2 or any(
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,50}", part.strip())
        for part in parts
    ):
        return []
    return list(dict.fromkeys(part.strip() for part in parts))


def _discover_covered_models(document: Document) -> tuple[list[str], str] | None:
    """Find declared models in metadata, explicit headings, or manual titles."""
    declared = document.metadata.get("covered_models")
    if isinstance(declared, (list, tuple)) and declared and all(
        isinstance(model, str) and model.strip() for model in declared
    ):
        return list(dict.fromkeys(model.strip() for model in declared)), "document_coverage"
    sources = [document.title or ""]
    sources.extend(
        block.text for block in document.blocks
        if isinstance(block, TextBlock) and block.kind == "heading"
    )
    # PDF ingestion often supplies no metadata title and classifies cover
    # headings as ordinary paragraphs. Inspect only short first-page lines,
    # not arbitrary body prose that could mention other machines.
    for block in document.blocks[:8]:
        if not isinstance(block, TextBlock) or block.page not in (None, 1):
            continue
        for line in block.text.splitlines()[:5]:
            if len(line.strip()) <= 100:
                sources.append(line.strip())
    for source in sources:
        match = re.search(r"\bmodels?\s*[:：]\s*([^\n.;]+)", source, re.I)
        if match:
            models = _model_list(match.group(1))
            if models:
                return models, "explicit_model_enumeration"
        # A title explicitly identifying a user/owner/service manual and
        # enumerating its covered models is also a coverage declaration.
        match = re.fullmatch(
            r"\s*(.+?)\s+(?:user|owner'?s|service|instruction)\s+manual\s*",
            source, re.I,
        )
        if match:
            models = _model_list(match.group(1))
            if models:
                return models, "manual_title_coverage"
    return None


def _explicit_model_scope(document: Document, block) -> tuple[list[str], str] | None:
    """Resolve explicit document coverage and narrower section/table exceptions.

    The upstream document reader or semantic worker supplies identities; this
    stage never guesses identities from punctuation or model-name morphology.
    """
    metadata = document.metadata
    discovered = _discover_covered_models(document)
    if discovered is None:
        return None
    covered, basis = discovered
    sections = metadata.get("model_scopes", {})
    if not isinstance(sections, dict):
        sections = {}
    explicit = None
    for heading in getattr(block, "heading_path", ()):
        if heading in sections:
            explicit = sections[heading]
            basis = "explicit_section_scope"
    if explicit is None:
        for heading in reversed(getattr(block, "heading_path", ())):
            # Prefer explicit section headings such as "X7PRO controls".
            # Require identifier boundaries so X7 does not match X7PRO.
            matched = [
                model for model in covered
                if re.search(
                    r"(?<![A-Za-z0-9])" + re.escape(model) + r"(?![A-Za-z0-9])",
                    heading, re.I,
                )
            ]
            if matched and len(matched) < len(covered):
                explicit = matched
                basis = "section_model_mention"
                break
    if isinstance(block, TableBlock) and block.subject_hint in sections:
        explicit = sections[block.subject_hint]
        basis = "explicit_table_scope"
    elif isinstance(block, TableBlock) and block.subject_hint and explicit is None:
        matched = [
            model for model in covered
            if re.search(
                r"(?<![A-Za-z0-9])" + re.escape(model) + r"(?![A-Za-z0-9])",
                block.subject_hint, re.I,
            )
        ]
        if matched and len(matched) < len(covered):
            explicit = matched
            basis = "table_model_mention"
    if explicit is not None:
        if not isinstance(explicit, (list, tuple)) or not explicit or any(
            model not in covered for model in explicit
        ):
            return [], "invalid_explicit_model_scope"  # Retain evidence and force canonical hold.
        covered = list(dict.fromkeys(explicit))
    return covered, basis


def _attach_model_scope(document: Document, block, observations: list[EvidenceObservation]) -> list[EvidenceObservation]:
    resolved = _explicit_model_scope(document, block)
    if resolved is None:
        return observations
    models, basis = resolved
    scope_context = (
        {"applicable_models": list(models), "applicability_basis": basis}
        if models else {"applicability_unresolved": basis}
    )
    return [
        replace(observation, context={**observation.context, **scope_context})
        for observation in observations
    ]


def process_document(document: Document) -> list[EvidenceObservation]:
    """Recover structure first; sentence-analyze prose only after it is known.

    Tables and figures are interpreted before ordinary text. Explicit structural
    references are resolved before prose is diagrammed, so grammar consumes
    structural context rather than competing with it. Final observation order
    still follows document block order for compatibility.
    """
    refs = resolve_cross_references(document)
    refs_by_source: dict[str, list[object]] = {}
    for ref in refs:
        refs_by_source.setdefault(ref.source_block_id, []).append(ref)

    prepared: dict[str, list[EvidenceObservation]] = {}

    # Pass 1: structural blocks. Table row/column binding and figure/callout
    # association must exist before ordinary prose is sentence-analyzed.
    for block in document.blocks:
        if isinstance(block, TableBlock):
            prepared[block.block_id] = _attach_model_scope(
                document, block, _table_observations(document, block)
            )
        elif isinstance(block, FigureBlock):
            prepared[block.block_id] = _attach_model_scope(
                document, block, _figure_observations(document, block)
            )

    # Pass 2: prose. Sentence analysis is deliberately last among block types.
    for block in document.blocks:
        if not isinstance(block, TextBlock):
            continue
        prepared[block.block_id] = _attach_model_scope(
            document,
            block,
            _text_observations(
                document,
                block,
                structural_refs=refs_by_source.get(block.block_id, ()),
            ),
        )

    observations: list[EvidenceObservation] = []
    for block in document.blocks:
        observations.extend(prepared.get(block.block_id, ()))
    for ref in refs:
        observations.append(EvidenceObservation(
            kind="cross_reference",
            source=SourceRef(document.source_id, ref.source_block_id, ref.text),
            value=ref.label,
            property_hint=ref.kind,
            context={"target_block_id": ref.target_block_id},
            ambiguous=ref.target_block_id is None,
        ))
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
