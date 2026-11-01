from __future__ import annotations

import csv
from pathlib import Path
from typing import TextIO

from evidencemill.document import Document, TableBlock


def parse_csv_stream(
    stream: TextIO,
    *,
    source_id: str,
    delimiter: str | None = None,
    header_rows: int | None = None,
    row_header_columns: int = 1,
) -> Document:
    if delimiter is None:
        sample = stream.read(4096)
        stream.seek(0)
        try:
            delimiter = csv.Sniffer().sniff(sample).delimiter
        except csv.Error:
            delimiter = ","
    rows = tuple(tuple(cell.strip() for cell in row) for row in csv.reader(stream, delimiter=delimiter))
    block = TableBlock(
        rows=rows,
        block_id="table-1",
        header_rows=header_rows,
        row_header_columns=row_header_columns,
    )
    return Document(source_id=source_id, blocks=(block,))


def parse_csv(path: str | Path, *, source_id: str | None = None, **kwargs) -> Document:
    p = Path(path)
    with p.open("r", encoding="utf-8-sig", newline="") as stream:
        return parse_csv_stream(stream, source_id=source_id or p.name, **kwargs)
