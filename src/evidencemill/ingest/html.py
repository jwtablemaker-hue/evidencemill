from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from evidencemill.document import Document, FigureBlock, TableBlock, TextBlock


_BLOCK_TAGS = {"p", "li", "dt", "dd", "blockquote", "pre"}
_HEADING_TAGS = {f"h{i}" for i in range(1, 7)}


class _Collector(HTMLParser):
    def __init__(self, source_id: str):
        super().__init__(convert_charrefs=True)
        self.source_id = source_id
        self.blocks = []
        self.heading_path: list[str] = []
        self.counter = 0
        self.hidden_depth = 0
        self.current_tag: str | None = None
        self.current_text: list[str] = []
        self.current_heading_level: int | None = None
        self.in_table = False
        self.table_rows: list[list[str]] = []
        self.table_row: list[str] | None = None
        self.cell_text: list[str] | None = None
        self.cell_is_header = False
        self.table_header_row_count = 0
        self.table_caption: list[str] | None = None
        self.table_caption_text: str | None = None
        self.in_figure = False
        self.figure_caption: list[str] | None = None
        self.figure_alt: list[str] = []

    def _next_id(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}-{self.counter}"

    def _flush_text(self):
        if not self.current_tag:
            return
        text = " ".join("".join(self.current_text).split()).strip()
        tag = self.current_tag
        level = self.current_heading_level
        self.current_tag = None
        self.current_text = []
        self.current_heading_level = None
        if not text:
            return
        if level is not None:
            self.heading_path[:] = self.heading_path[: max(0, level - 1)]
            self.heading_path.append(text)
            self.blocks.append(TextBlock(text=text, block_id=self._next_id("heading"), kind="heading", heading_path=tuple(self.heading_path)))
        else:
            self.blocks.append(TextBlock(text=text, block_id=self._next_id("text"), kind="paragraph" if tag != "li" else "list_item", heading_path=tuple(self.heading_path)))

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attr = dict(attrs)
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden_depth += 1
            return
        if self.hidden_depth:
            return
        if tag == "table":
            self._flush_text()
            self.in_table = True
            self.table_rows = []
            self.table_header_row_count = 0
            self.table_caption_text = None
            return
        if self.in_table:
            if tag == "caption":
                self.table_caption = []
            elif tag == "tr":
                self.table_row = []
                self.cell_is_header = False
            elif tag in {"th", "td"}:
                self.cell_text = []
                if tag == "th":
                    self.cell_is_header = True
            return
        if tag == "figure":
            self._flush_text()
            self.in_figure = True
            self.figure_alt = []
            self.figure_caption = None
            return
        if self.in_figure:
            if tag == "figcaption":
                self.figure_caption = []
            elif tag == "img":
                alt = (attr.get("alt") or "").strip()
                if alt:
                    self.figure_alt.append(alt)
            return
        if tag in _HEADING_TAGS:
            self._flush_text()
            self.current_tag = tag
            self.current_heading_level = int(tag[1])
            return
        if tag in _BLOCK_TAGS:
            self._flush_text()
            self.current_tag = tag
            return
        if tag == "img":
            alt = (attr.get("alt") or "").strip()
            src = (attr.get("src") or "").strip() or None
            if alt or src:
                self.blocks.append(FigureBlock(block_id=self._next_id("figure"), caption=alt or None, heading_path=tuple(self.heading_path), source_path=src))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)
            return
        if self.hidden_depth:
            return
        if self.in_table:
            if tag in {"th", "td"} and self.cell_text is not None and self.table_row is not None:
                self.table_row.append(" ".join("".join(self.cell_text).split()).strip())
                self.cell_text = None
            elif tag == "tr" and self.table_row is not None:
                if any(self.table_row):
                    self.table_rows.append(self.table_row)
                    if self.cell_is_header and len(self.table_rows) == self.table_header_row_count + 1:
                        self.table_header_row_count += 1
                self.table_row = None
            elif tag == "caption" and self.table_caption is not None:
                self.table_caption_text = " ".join("".join(self.table_caption).split()).strip() or None
                self.table_caption = None
            elif tag == "table":
                self.in_table = False
                if self.table_rows:
                    self.blocks.append(TableBlock(rows=tuple(tuple(row) for row in self.table_rows), block_id=self._next_id("table"), caption=self.table_caption_text, heading_path=tuple(self.heading_path), header_rows=max(1, self.table_header_row_count)))
            return
        if self.in_figure:
            if tag == "figcaption" and self.figure_caption is not None:
                return
            if tag == "figure":
                caption = None
                if self.figure_caption is not None:
                    caption = " ".join("".join(self.figure_caption).split()).strip() or None
                if caption is None and self.figure_alt:
                    caption = "; ".join(self.figure_alt)
                self.blocks.append(FigureBlock(block_id=self._next_id("figure"), caption=caption, heading_path=tuple(self.heading_path)))
                self.in_figure = False
                self.figure_caption = None
                self.figure_alt = []
            return
        if tag == self.current_tag or tag in _HEADING_TAGS and self.current_heading_level:
            self._flush_text()

    def handle_data(self, data):
        if self.hidden_depth:
            return
        if self.in_table:
            if self.cell_text is not None:
                self.cell_text.append(data)
            elif self.table_caption is not None:
                self.table_caption.append(data)
            return
        if self.in_figure:
            if self.figure_caption is not None:
                self.figure_caption.append(data)
            return
        if self.current_tag:
            self.current_text.append(data)


def parse_html(text: str, *, source_id: str, title: str | None = None) -> Document:
    parser = _Collector(source_id)
    parser.feed(text)
    parser.close()
    parser._flush_text()
    return Document(source_id=source_id, title=title, blocks=tuple(parser.blocks))


def parse_html_file(path: str | Path, *, source_id: str | None = None) -> Document:
    p = Path(path)
    return parse_html(p.read_text(encoding="utf-8", errors="replace"), source_id=source_id or p.name)
