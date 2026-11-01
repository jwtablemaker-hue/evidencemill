# EvidenceMill

EvidenceMill turns source documents into structured, traceable evidence before an expensive semantic model has to touch them.

It is deliberately domain-neutral. It does not decide truth and it does not write canonical facts.

## What it handles

Current deterministic paths:

- Plain text and Markdown: headings, paragraphs, sentence structure, quantities, units, component attachment, multiplicity, placement, qualifiers, and scope.
- HTML: headings, paragraphs, lists, tables, captions, figures, and cross-references.
- CSV/TSV: table structure, row and column context, inherited units, and cell observations.
- PDF: positioned text blocks, detected tables, embedded-image regions, document metadata, and optional OCR fallback for scanned pages.
- Images: OCR word boxes, diagram callout candidates, and geometric callout-to-label association.
- Diagrams: optional OpenCV leader-line detection.
- Cross-references: Figure, Table, Section, and Appendix references resolved to extracted blocks when possible.
- SQL: portable mapping from EvidenceMill observations into existing SQL schemas.

## Pipeline

    source file
      -> document ingestion
      -> layout blocks
      -> prose / table / figure extraction
      -> cross-reference resolution
      -> structured EvidenceObservation records
      -> FactPrepWorker
      -> READY fact candidates / REVIEW residue
      -> SQLite staging or optional domain adapter
      -> unresolved semantics only
      -> downstream system

## Cheap core, optional heavy edges

The core package uses only the Python standard library.

Optional extras add capabilities only when needed:

    pip install evidencemill[pdf]
    pip install evidencemill[ocr]
    pip install evidencemill[vision]
    pip install evidencemill[all]

Image OCR uses pytesseract and therefore also needs a working Tesseract installation.

## CLI

After installation:

    evidencemill manual.html --pretty
    evidencemill manual.pdf --ocr --pretty
    evidencemill specs.csv --pretty

The output is JSON containing document metadata and structured observations.

## Design rules

- Preserve exact source text and location.
- Structure before semantics.
- Deterministic work stays deterministic.
- Never invent missing subjects, relationships, units, or applicability.
- Ambiguity is valid output, not failure.
- Every observation remains traceable to source evidence.
- The extraction core stays domain-neutral.
- Downstream schemas belong in adapters or external mapping files.

## Fact-prep worker

The fact-prep worker converts structural observations into stable, evidence-backed
fact candidates without pretending to know a downstream domain.

Candidates are marked:

- `READY` when subject, predicate, value, unit and structural scope are explicit enough for staging.
- `REVIEW` when applicability, rating basis, subject identity or another semantic detail remains unresolved.

The worker preserves the source locator and text on every candidate and uses stable
candidate IDs, so repeated parsing updates the same staging row instead of multiplying
duplicates.

Examples:

    evidencemill manual.html --facts --pretty
    evidencemill specs.csv --facts --sqlite-staging facts.sqlite
    evidencemill manual.md notes.html specs.csv --benchmark 20

SQLite staging is deliberately pre-canonical. A downstream system can map or reconcile
`READY` candidates into its own schema while review workers see only the unresolved residue.

## SQL integration

The SQL adapter maps target columns to neutral observation paths such as value, unit, source.source_id, source.location, source.raw_text, subject_hint, property_hint, qualifiers, context, and ambiguous.

SQLite schema introspection and conservative mapping suggestions are built in. The same mapping contract can generate parameterized SQL for standard DB-API placeholder styles.

See docs/sql-adapter.md.

## Status

EvidenceMill is an early functional extraction engine. Text, HTML, CSV/table context, cross-reference resolution, diagram callout geometry, fact preparation, benchmarking, and SQLite staging are implemented. PDF, OCR, and computer-vision paths are optional integrations and depend on their external libraries.

## Support

If EvidenceMill is useful to you, sponsorship helps cover CI, hosted build, and project infrastructure costs.
