# EvidenceMill

Document interpretation infrastructure for turning prose, tables, diagrams, and layout into structured, traceable evidence.

EvidenceMill sits before domain-specific systems. It does not decide truth and it does not write canonical facts. It removes cheap, repetitive interpretation work from agents by extracting explicit document structure deterministically.

## Pipeline

    source document
      -> layout
      -> prose / tables / illustrations
      -> cross-reference resolution
      -> structured evidence observations
      -> domain or SQL adapter
      -> unresolved semantics only
      -> downstream system

## Design rules

- Preserve exact source text and location.
- Structure before semantics.
- Deterministic work stays deterministic.
- Never invent missing subjects, relationships, units, or applicability.
- Ambiguity is valid output, not failure.
- Every observation remains traceable to source evidence.
- The extraction core stays domain-neutral.
- Downstream schemas belong in adapters or external mapping files.

## Initial modules

- sentence_structure: quantities, units, component mentions, placement, multiplicity, qualifiers, system-vs-component scope.
- table_context: row headers, column headers, inherited units, notes, and explicit cell context.
- layout: neutral block, caption, and heading interfaces.
- illustration: neutral callout, label, and leader-line interfaces.
- adapters.sql: portable table/column mapping from observations into existing SQL schemas.

## SQL integration

EvidenceMill does not need to know a target database's domain model.

The SQL adapter maps target columns to neutral observation paths such as:

    value
    unit
    source.source_id
    source.location
    source.raw_text
    subject_hint
    property_hint
    qualifiers
    context
    ambiguous

SQLite schema introspection and conservative mapping suggestions are built in.
The same mapping contract can generate parameterized SQL for DB-API qmark,
format, numeric, named, and pyformat styles.

See docs/sql-adapter.md.

## Status

Early extraction engine. It produces evidence observations, not autonomous facts.
