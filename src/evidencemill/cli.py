from __future__ import annotations

import argparse
from dataclasses import asdict
from contextlib import redirect_stdout
import json
import sqlite3
import sys

from evidencemill.benchmark import benchmark_paths
from evidencemill.fact_sql import stage_candidates_sqlite
from evidencemill.pipeline import ingest_path, process_document
from evidencemill.worker import FactPrepWorker


def _emit(payload, *, pretty: bool) -> None:
    json.dump(
        payload,
        sys.stdout,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        ensure_ascii=False,
    )
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidencemill")
    parser.add_argument("inputs", nargs="+", help="Documents to extract")
    parser.add_argument("--source-id", default=None, help="Override source id for a single input")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--ocr", action="store_true", help="OCR scanned PDF pages when text is absent")
    parser.add_argument("--facts", action="store_true", help="Run the fact-prep worker")
    parser.add_argument(
        "--facts-only",
        action="store_true",
        help="Emit fact candidates and report without serializing observations",
    )
    parser.add_argument("--sqlite-staging", default=None, metavar="DB", help="Stage fact candidates into SQLite")
    parser.add_argument("--benchmark", type=int, default=0, metavar="REPEATS", help="Benchmark the input set")
    args = parser.parse_args(argv)

    if args.source_id and len(args.inputs) != 1:
        parser.error("--source-id is valid only with one input")

    if args.benchmark:
        with redirect_stdout(sys.stderr):
            result = benchmark_paths(args.inputs, repeats=args.benchmark, ocr=args.ocr)
        _emit({"benchmark": result.to_dict()}, pretty=args.pretty)
        return 0

    worker = FactPrepWorker()
    outputs = []
    staged = 0
    connection = sqlite3.connect(args.sqlite_staging) if args.sqlite_staging else None

    try:
        for index, path in enumerate(args.inputs):
            source_id = args.source_id if index == 0 else None
            # Library notices must never contaminate the machine-readable output.
            with redirect_stdout(sys.stderr):
                document = ingest_path(path, source_id=source_id, ocr=args.ocr)
                observations = process_document(document)
            payload = {
                "document": {
                    "source_id": document.source_id,
                    "title": document.title,
                    "metadata": document.metadata,
                    "block_count": len(document.blocks),
                },
            }
            if not args.facts_only:
                payload["observations"] = [asdict(item) for item in observations]

            if args.facts or args.facts_only or connection is not None:
                result = worker.run_observations(observations, source_id=document.source_id)
                payload["fact_candidates"] = [item.to_dict() for item in result.candidates]
                payload["worker_report"] = result.report.to_dict()
                if connection is not None:
                    staged += stage_candidates_sqlite(connection, result.candidates)

            outputs.append(payload)

        if connection is not None:
            connection.commit()
    finally:
        if connection is not None:
            connection.close()

    result_payload = outputs[0] if len(outputs) == 1 else {"documents": outputs}
    if args.sqlite_staging:
        result_payload["sqlite_staging"] = {
            "path": args.sqlite_staging,
            "rows_processed": staged,
        }
    _emit(result_payload, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
