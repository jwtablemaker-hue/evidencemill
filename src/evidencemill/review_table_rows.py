#!/usr/bin/env python3
"""Flag text in merged native PDF cells for review using an adjacent row label."""

import argparse
from contextlib import redirect_stdout
import hashlib
import json
import sys
from pathlib import Path


def words_in(words, box):
    x0, y0, x1, y1 = box
    return [
        word for word in words
        if x0 <= (word[0] + word[2]) / 2 < x1
        and y0 <= (word[1] + word[3]) / 2 < y1
    ]


def row_suggestions(table, words):
    for index, (previous, current) in enumerate(zip(table.rows, table.rows[1:]), 1):
        for column, (merged, empty) in enumerate(zip(previous.cells, current.cells)):
            if column == 0 or merged is None or empty is not None:
                continue
            above, label = previous.cells[column - 1], current.cells[column - 1]
            if not above or not label:
                continue
            # A single value cell must span exactly two individually bounded labels.
            if not (
                abs(merged[1] - above[1]) < 1 and abs(above[3] - label[1]) < 1
                and abs(merged[3] - label[3]) < 1 and abs(label[2] - merged[0]) < 1
            ):
                continue
            upper_box = (merged[0], merged[1], merged[2], label[1])
            lower_box = (merged[0], label[1], merged[2], merged[3])
            upper, lower, labels = (words_in(words, box) for box in (upper_box, lower_box, label))
            if not upper or not lower or not labels:
                continue
            # Refuse to split a glyph/word crossing the inferred separator.
            if any(w[3] > label[1] for w in upper) or any(w[1] < label[1] for w in lower):
                continue
            yield {
                "row": index + 1,
                "column": column + 1,
                "row_label": " ".join(w[4] for w in labels),
                "candidate_value": " ".join(w[4] for w in lower),
                "value_region": lower_box,
                "word_boxes": [w[:5] for w in lower],
                "review_status": "Unverified row association",
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--sheet", type=int, required=True, help="One-based PDF sheet")
    args = parser.parse_args()

    import fitz  # Existing EvidenceMill PDF dependency

    with args.pdf.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    with fitz.open(args.pdf) as document:
        if not 1 <= args.sheet <= len(document):
            parser.error("Sheet is outside this PDF")
        page = document[args.sheet - 1]
        words = page.get_text("words", sort=True)
        with redirect_stdout(sys.stderr):
            tables = page.find_tables().tables
        for table_number, table in enumerate(tables, 1):
            for suggestion in row_suggestions(table, words):
                print(json.dumps({
                    "source_capture_sha256": digest, "sheet": args.sheet,
                    "table": table_number, **suggestion,
                }))


if __name__ == "__main__":
    main()
