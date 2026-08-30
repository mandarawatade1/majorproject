"""PDF -> ParsedDocument, with page numbers on every section.

Page-level provenance is a hard requirement of this project: a citation must
be able to say "Annual Report 2023-24, section 4.2, page 37". Everything here
serves that.

Heading detection uses three strategies in descending order of reliability:

1. The PDF's embedded table of contents. Institutional PDFs produced from Word
   (annual reports, NAAC submissions, IQAC reports) almost always carry one,
   and it is authoritative — it is the author's own structure.
2. Font-size analysis. Text noticeably larger than the document's body size is
   treated as a heading, with levels assigned by size rank.
3. One section per page. Always correct, never useful, but it guarantees page
   provenance even for a scanned or badly generated file.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from pathlib import Path

from rag.ingestion.categorise import categorise, infer_department
from rag.ingestion.models import ParsedDocument, Section, SourceType, slugify

MIN_USEFUL_CHARS = 400
HEADING_SIZE_RATIO = 1.15
"""A span must be this much larger than body text to count as a heading."""

import re

_PAGE_NUMBER_LIKE = re.compile(r"^(page\s*)?\d{1,4}$", re.IGNORECASE)


def _looks_like_page_number(text: str) -> bool:
    """True for printed page-number labels ("Page 36", "36", "- 36 -").

    Font-size analysis alone cannot tell a real heading from a page number
    printed in a large running header or footer -- both are short and
    large. Rejecting anything that is just digits (with an optional "Page"
    prefix) keeps a footer artifact from becoming a section heading whose
    number then disagrees with the section's real `start_page`.
    """
    return bool(_PAGE_NUMBER_LIKE.match(text.strip().strip("-").strip()))


def parse_pdf(
    path: Path,
    *,
    source_url: str | None = None,
    fetched_at: str | None = None,
    title: str | None = None,
    extract_tables: bool = False,
    min_chars: int = MIN_USEFUL_CHARS,
) -> ParsedDocument | None:
    """Parse a PDF. Returns None if too little text could be extracted.

    A None return on a large file usually means the PDF is scanned images, in
    which case OCR is required — reported by the CLI rather than silently
    dropped, because a missing annual report is a corpus gap worth knowing
    about.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("PyMuPDF is required to parse PDFs: pip install pymupdf") from exc

    with fitz.open(path) as document:
        pages = [page.get_text("text") for page in document]
        toc = document.get_toc() or []
        metadata = document.metadata or {}
        page_count = document.page_count
        spans = _collect_spans(document) if not toc else []

    full_text = "\n\n".join(pages).strip()
    if len(full_text) < min_chars:
        return None

    resolved_title = (
        title
        or (metadata.get("title") or "").strip()
        or path.stem.replace("-", " ").replace("_", " ").title()
    )

    if toc:
        sections = _sections_from_toc(toc, pages, resolved_title)
    elif spans:
        sections = _sections_from_spans(spans, pages, resolved_title)
    else:
        sections = _sections_per_page(pages, resolved_title)

    if extract_tables:
        _append_tables(path, sections)

    reference = source_url or str(path)
    return ParsedDocument(
        doc_id=_doc_id_for(path, source_url),
        title=resolved_title,
        source_type=SourceType.WEB_PDF,
        category=categorise(reference),
        text=full_text,
        sections=sections,
        source_url=source_url,
        local_path=str(path),
        fetched_at=fetched_at or datetime.now(UTC).isoformat(),
        department=infer_department(reference, full_text),
        author=(metadata.get("author") or "").strip() or None,
        published_date=_normalise_pdf_date(metadata.get("creationDate")),
        page_count=page_count,
        is_demo=False,
    )


# ---------------------------------------------------------------------------
# Strategy 1: embedded table of contents
# ---------------------------------------------------------------------------


def _sections_from_toc(toc: list[list], pages: list[str], root_title: str) -> list[Section]:
    """Build sections from [level, title, page] entries.

    Each entry's content runs from its own start page to the page before the
    next entry, which is why start_page and end_page are both meaningful.
    """
    sections: list[Section] = []
    open_stack: list[tuple[int, int]] = []

    for i, entry in enumerate(toc):
        level, heading, page_no = int(entry[0]), str(entry[1]).strip(), int(entry[2])
        start = max(1, page_no)
        end = int(toc[i + 1][2]) - 1 if i + 1 < len(toc) else len(pages)
        end = max(start, min(end, len(pages)))

        content = "\n\n".join(pages[start - 1 : end]).strip()

        while open_stack and open_stack[-1][0] >= level:
            open_stack.pop()
        parent_index = open_stack[-1][1] if open_stack else None
        ancestors = [sections[idx].heading for _, idx in open_stack]
        section_path = " > ".join([root_title, *ancestors, heading])

        index = len(sections)
        sections.append(
            Section(
                heading=heading,
                level=level,
                content=content,
                order_index=index,
                section_path=section_path,
                parent_index=parent_index,
                start_page=start,
                end_page=end,
            )
        )
        open_stack.append((level, index))

    return sections or _sections_per_page(pages, root_title)


# ---------------------------------------------------------------------------
# Strategy 2: font-size analysis
# ---------------------------------------------------------------------------


def _collect_spans(document: object) -> list[tuple[int, float, str]]:
    """Return (page_number, font_size, text) for every non-empty span."""
    spans: list[tuple[int, float, str]] = []
    for page_index, page in enumerate(document, start=1):  # type: ignore[attr-defined]
        try:
            data = page.get_text("dict")
        except Exception:
            continue
        for block in data.get("blocks", []):
            for line in block.get("lines", []):
                text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
                if not text:
                    continue
                sizes = [
                    s.get("size", 0.0) for s in line.get("spans", []) if s.get("text", "").strip()
                ]
                if sizes:
                    spans.append((page_index, max(sizes), text))
    return spans


def _sections_from_spans(
    spans: list[tuple[int, float, str]], pages: list[str], root_title: str
) -> list[Section]:
    """Treat spans meaningfully larger than body text as headings."""
    sizes = [size for _, size, _ in spans]
    body_size = statistics.median(sizes) if sizes else 0.0
    threshold = body_size * HEADING_SIZE_RATIO

    heading_sizes = sorted({round(s, 1) for s in sizes if s >= threshold}, reverse=True)
    level_of = {size: min(i + 1, 6) for i, size in enumerate(heading_sizes[:6])}

    sections: list[Section] = []
    current_heading = root_title
    current_level = 1
    current_page = 1
    buffer: list[str] = []

    def flush(end_page: int) -> None:
        content = "\n".join(buffer).strip()
        if not content:
            return
        index = len(sections)
        sections.append(
            Section(
                heading=current_heading,
                level=current_level,
                content=content,
                order_index=index,
                section_path=f"{root_title} > {current_heading}"
                if current_heading != root_title
                else root_title,
                start_page=current_page,
                end_page=end_page,
            )
        )

    for page_no, size, text in spans:
        rounded = round(size, 1)
        is_heading = (
            rounded in level_of
            and 3 <= len(text) <= 120
            and not _looks_like_page_number(text)
        )
        if is_heading:
            flush(page_no)
            buffer = []
            current_heading = text
            current_level = level_of[rounded]
            current_page = page_no
        else:
            buffer.append(text)

    flush(len(pages))
    return sections or _sections_per_page(pages, root_title)


# ---------------------------------------------------------------------------
# Strategy 3: one section per page
# ---------------------------------------------------------------------------


def _sections_per_page(pages: list[str], root_title: str) -> list[Section]:
    sections: list[Section] = []
    for page_index, text in enumerate(pages, start=1):
        content = text.strip()
        if not content:
            continue
        sections.append(
            Section(
                heading=f"Page {page_index}",
                level=1,
                content=content,
                order_index=len(sections),
                section_path=f"{root_title} > Page {page_index}",
                start_page=page_index,
                end_page=page_index,
            )
        )
    return sections


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def _append_tables(path: Path, sections: list[Section]) -> None:
    """Append markdown tables to whichever section covers their page.

    Institutional PDFs carry a lot of meaning in tables — intake numbers,
    placement statistics, committee membership. Flattened to prose by plain
    text extraction they become unreadable; as markdown the LLM can read them.
    """
    try:
        import pdfplumber
    except ImportError:
        return

    try:
        with pdfplumber.open(path) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                for table in page.extract_tables() or []:
                    markdown = _table_to_markdown(table)
                    if not markdown:
                        continue
                    target = _section_covering(sections, page_index)
                    if target is not None:
                        target.content = f"{target.content}\n\n{markdown}".strip()
    except Exception:
        # Table extraction is a bonus; never let it fail an ingest.
        return


def _section_covering(sections: list[Section], page_no: int) -> Section | None:
    for section in sections:
        if (
            section.start_page is not None
            and section.end_page is not None
            and section.start_page <= page_no <= section.end_page
        ):
            return section
    return sections[-1] if sections else None


def _table_to_markdown(table: list[list[str | None]]) -> str:
    rows = [[(cell or "").replace("\n", " ").strip() for cell in row] for row in table if row]
    rows = [r for r in rows if any(r)]
    if len(rows) < 2:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header, *body = rows
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc_id_for(path: Path, source_url: str | None) -> str:
    if source_url:
        from urllib.parse import urlparse

        parts = urlparse(source_url)
        host = parts.netloc.replace("www.", "").split(".")[0]
        stem = Path(parts.path).stem or path.stem
        return f"{host}-pdf-{slugify(stem)}"
    return f"pdf-{slugify(path.stem)}"


def _normalise_pdf_date(raw: str | None) -> str | None:
    """PDF dates look like D:20250214093000+05'30'."""
    if not raw or not raw.startswith("D:") or len(raw) < 10:
        return None
    digits = raw[2:10]
    if not digits.isdigit():
        return None
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
