from __future__ import annotations

import re

from evidencemill.document import Document, TextBlock


_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return False
    if _MD_HEADING.match(stripped):
        return True
    letters = [c for c in stripped if c.isalpha()]
    return bool(letters) and len(letters) >= 3 and stripped.upper() == stripped and not stripped.endswith(".")


def parse_text(text: str, *, source_id: str, title: str | None = None) -> Document:
    blocks: list[TextBlock] = []
    heading_path: list[str] = []
    paragraph: list[str] = []
    counter = 0

    def flush() -> None:
        nonlocal counter
        if not paragraph:
            return
        counter += 1
        value = " ".join(part.strip() for part in paragraph if part.strip()).strip()
        paragraph.clear()
        if value:
            blocks.append(TextBlock(
                text=value,
                block_id=f"text-{counter}",
                kind="paragraph",
                heading_path=tuple(heading_path),
            ))

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        match = _MD_HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            heading = match.group(2).strip()
            heading_path[:] = heading_path[:max(0, level - 1)]
            heading_path.append(heading)
            counter += 1
            blocks.append(TextBlock(
                text=heading,
                block_id=f"heading-{counter}",
                kind="heading",
                heading_path=tuple(heading_path),
            ))
        elif _looks_like_heading(line):
            flush()
            heading_path[:] = [line]
            counter += 1
            blocks.append(TextBlock(
                text=line,
                block_id=f"heading-{counter}",
                kind="heading",
                heading_path=tuple(heading_path),
            ))
        else:
            paragraph.append(line)
    flush()
    return Document(source_id=source_id, title=title, blocks=tuple(blocks))
