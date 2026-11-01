# Architecture

EvidenceMill separates document mechanics from semantic judgment.

    input
      -> ingestion adapter
      -> Document blocks
      -> deterministic structural extractors
      -> EvidenceObservation stream
      -> optional SQL/domain adapter
      -> unresolved residue

## Ingestion adapters

The text, HTML, CSV, PDF, and image adapters all produce the same neutral
Document representation. A document contains positioned TextBlock, TableBlock,
and FigureBlock records with source identity and local structure.

## Structural extractors

Text is split into statements and passed through sentence_structure.
Tables preserve row headers, column headers, values, and inherited units.
Figures preserve OCR word boxes and callout geometry.
Cross-reference resolution links explicit Figure/Table/Section references to
known blocks where possible.

No stage is allowed to silently convert an uncertain observation into a fact.

## Optional dependencies

PDF extraction uses PyMuPDF. OCR uses Pillow and pytesseract. Straight-line
detection uses OpenCV. These dependencies are kept out of the base install so
plain text, HTML, CSV, SQL mapping, and deterministic parsing remain light.

## Downstream boundary

EvidenceObservation is the public boundary. Domain-specific identity,
vocabulary, reconciliation, provenance admission, conflict policy, and final
publication remain downstream concerns.
