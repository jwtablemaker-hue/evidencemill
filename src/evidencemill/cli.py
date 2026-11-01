from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys

from evidencemill.pipeline import ingest_path, process_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidencemill")
    parser.add_argument("input", help="Document to extract")
    parser.add_argument("--source-id", default=None)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--ocr", action="store_true", help="OCR scanned PDF pages when text is absent")
    args = parser.parse_args(argv)

    document = ingest_path(args.input, source_id=args.source_id, ocr=args.ocr)
    observations = process_document(document)
    payload = {
        "document": {"source_id": document.source_id, "title": document.title, "metadata": document.metadata, "block_count": len(document.blocks)},
        "observations": [asdict(item) for item in observations],
    }
    json.dump(payload, sys.stdout, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":"), ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
