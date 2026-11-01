"""EvidenceMill: deterministic document structure extraction."""

from .document import Document, FigureBlock, OcrWord, TableBlock, TextBlock
from .models import EvidenceObservation, SourceRef
from .pipeline import ingest_path, process_document
from .sentence_structure import analyze_statement
from .table_context import parse_table

__all__ = [
    "Document",
    "EvidenceObservation",
    "FigureBlock",
    "OcrWord",
    "SourceRef",
    "TableBlock",
    "TextBlock",
    "analyze_statement",
    "ingest_path",
    "parse_table",
    "process_document",
]
