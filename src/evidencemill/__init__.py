"""EvidenceMill: deterministic document structure extraction."""

from .document import Document, FigureBlock, OcrWord, TableBlock, TextBlock
from .fact_sql import create_sqlite_fact_staging, stage_candidates_sqlite
from .models import EvidenceObservation, SourceRef
from .pipeline import ingest_path, process_document
from .sentence_structure import analyze_statement
from .table_context import parse_table
from .worker import FactCandidate, FactPrepWorker, WorkerReport, WorkerResult

__all__ = [
    "Document",
    "EvidenceObservation",
    "FactCandidate",
    "FactPrepWorker",
    "FigureBlock",
    "OcrWord",
    "SourceRef",
    "TableBlock",
    "TextBlock",
    "WorkerReport",
    "WorkerResult",
    "analyze_statement",
    "create_sqlite_fact_staging",
    "ingest_path",
    "parse_table",
    "process_document",
    "stage_candidates_sqlite",
]
