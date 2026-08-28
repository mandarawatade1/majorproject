"""Build a document's heading hierarchy from markdown.

This is the foundation of the "structure-aware" claim in the project abstract.
Chunking in Phase 4 splits *within* these sections and never across them, so a
chunk can always be traced back to a real heading path rather than to an
arbitrary character offset.
"""

from __future__ import annotations

import re

from rag.ingestion.models import Section

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$", re.M)
_CODE_FENCE_RE = re.compile(r"^```", re.M)


def sections_from_markdown(markdown: str, root_title: str = "") -> list[Section]:
    """Split markdown into Sections, preserving heading nesting.

    Text appearing before the first heading becomes a preamble section, so no
    content is ever silently dropped. `section_path` is the breadcrumb shown to
    the user in a citation.
    """
    markdown = _blank_out_fenced_code_headings(markdown)
    matches = list(_HEADING_RE.finditer(markdown))

    sections: list[Section] = []
    open_stack: list[tuple[int, int]] = []  # (level, index in `sections`)

    def path_for(level: int, heading: str) -> tuple[str, int | None]:
        while open_stack and open_stack[-1][0] >= level:
            open_stack.pop()
        parent_index = open_stack[-1][1] if open_stack else None
        ancestors = [sections[i].heading for _, i in open_stack]
        trail = [*ancestors, heading]
        if root_title and (not trail or trail[0] != root_title):
            trail = [root_title, *trail]
        return " > ".join(trail), parent_index

    # Preamble: content before the first heading.
    first_start = matches[0].start() if matches else len(markdown)
    preamble = markdown[:first_start].strip()
    if preamble:
        sections.append(
            Section(
                heading=root_title or "Introduction",
                level=1,
                content=preamble,
                order_index=0,
                section_path=root_title or "Introduction",
            )
        )

    for i, match in enumerate(matches):
        level = len(match.group(1))
        heading = match.group(2).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        content = markdown[body_start:body_end].strip()

        section_path, parent_index = path_for(level, heading)
        index = len(sections)
        sections.append(
            Section(
                heading=heading,
                level=level,
                content=content,
                order_index=index,
                section_path=section_path,
                parent_index=parent_index,
            )
        )
        open_stack.append((level, index))

    if not sections and markdown.strip():
        sections.append(
            Section(
                heading=root_title or "Document",
                level=1,
                content=markdown.strip(),
                order_index=0,
                section_path=root_title or "Document",
            )
        )
    return sections


def _blank_out_fenced_code_headings(markdown: str) -> str:
    """Stop '#' inside a fenced code block being read as a heading."""
    if "```" not in markdown:
        return markdown
    out: list[str] = []
    inside = False
    for line in markdown.splitlines():
        if _CODE_FENCE_RE.match(line):
            inside = not inside
            out.append(line)
        elif inside and line.lstrip().startswith("#"):
            out.append(line.replace("#", "⌗", 1))
        else:
            out.append(line)
    return "\n".join(out)
