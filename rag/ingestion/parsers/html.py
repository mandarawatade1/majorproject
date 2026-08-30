"""HTML -> ParsedDocument.

Boilerplate removal matters more than it sounds. A WordPress institutional
site repeats its 13-item navigation, sidebar and footer on every page. Indexed
naively, those become the highest-frequency text in the corpus and pollute
every retrieval. trafilatura strips them; this is the "low-information content
filtering" named in the project abstract, applied at the document level.
Chunk-level filtering follows in Phase 4.
"""

from __future__ import annotations

import html as html_module
import re
from datetime import UTC, datetime
from pathlib import Path

from rag.ingestion.categorise import categorise, infer_department
from rag.ingestion.models import DocumentCategory, ParsedDocument, SourceType, slugify
from rag.ingestion.parsers.sections import sections_from_markdown

MIN_USEFUL_CHARS = 250
"""Below this, a page is navigation furniture rather than content."""

MIN_WRAPPER_CHARS = 40
"""A much lower bar for the *known* .post-content wrapper: if that specific,
high-confidence selector matched at all, even a short result is real content
(a thin hub page), not navigation noise. MIN_USEFUL_CHARS stays high because
it guards the generic trafilatura/BeautifulSoup fallback, which has no such
confidence and needs a stricter bar against picking up junk."""

_DATE_RE = re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b")


def parse_html(
    html: str,
    url: str,
    *,
    local_path: Path | None = None,
    fetched_at: str | None = None,
    min_chars: int = MIN_USEFUL_CHARS,
) -> ParsedDocument | None:
    """Parse one HTML page. Returns None if it carries too little content."""
    title = _extract_title(html) or _title_from_url(url)
    markdown = _extract_main_content(html)

    if markdown is None or len(markdown.strip()) < min_chars:
        return None

    category = categorise(url)
    document = ParsedDocument(
        doc_id=_doc_id_for(url),
        title=title,
        source_type=SourceType.WEB_HTML,
        category=category,
        text=markdown,
        sections=sections_from_markdown(markdown, root_title=title),
        source_url=url,
        local_path=str(local_path) if local_path else None,
        fetched_at=fetched_at or datetime.now(UTC).isoformat(),
        department=infer_department(url, markdown),
        published_date=_extract_date(html),
        is_demo=False,
    )
    return document


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def _extract_main_content(html: str) -> str | None:
    """The theme's own content wrapper first; trafilatura/BeautifulSoup as
    fallbacks for anything not built on this template.

    This theme puts the real article inside a predictable, specific wrapper
    -- `div.column-medium > div.content-block > div.post-content` -- but
    also carries several sitewide chrome blocks (a "Departments" sidebar
    accordion, an "Announcements" sidebar feed, a WhatsApp click-to-chat
    popup, and the top nav menu) that are structurally indistinguishable
    from real content to a generic extractor. trafilatura's favor_recall
    mode picked up a different one of these each time an earlier one was
    excluded, so unrelated pages kept hashing identically. Targeting the
    theme's known wrapper directly sidesteps that guessing game entirely:
    if that wrapper exists, it is unambiguously the page's own content and
    nothing else needs to be excluded.
    """
    wrapper_text = _extract_post_content_wrapper(html)
    if wrapper_text and len(wrapper_text.strip()) >= MIN_WRAPPER_CHARS:
        return _tidy(wrapper_text)

    # Not built on the known template (or too little content in it) --
    # fall back to generic extraction, still with chrome stripped first.
    html = _strip_sidebar_widgets(html)

    try:
        import trafilatura

        extracted = trafilatura.extract(
            html,
            output_format="markdown",
            include_tables=True,
            include_comments=False,
            include_images=False,
            favor_recall=True,
        )
        if extracted and extracted.strip():
            return _tidy(extracted)
    except ImportError:
        pass
    except Exception:
        # A malformed page should degrade to the fallback, not kill the run.
        pass

    return _fallback_extract(html)


def _extract_post_content_wrapper(html: str) -> str | None:
    """Pull text from the theme's own `.post-content` wrapper, if present.

    Converted with trafilatura's own HTML-string extraction where possible
    so tables and lists still come out as markdown; falls back to the same
    heading/paragraph walk `_fallback_extract` uses otherwise.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None

    wrapper = soup.select_one("div.post-content")
    if wrapper is None:
        return None

    try:
        import trafilatura

        extracted = trafilatura.extract(
            str(wrapper),
            output_format="markdown",
            include_tables=True,
            include_comments=False,
            include_images=False,
        )
        if extracted and extracted.strip():
            return extracted
    except ImportError:
        pass
    except Exception:
        pass

    lines: list[str] = []
    for element in wrapper.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th"]):
        text = element.get_text(" ", strip=True)
        if text:
            lines.append(text)
    return "\n\n".join(lines) if lines else None


def _strip_sidebar_widgets(html: str) -> str:
    """Remove sidebar widget blocks that are the same across many pages.

    Best-effort: if BeautifulSoup is not installed, the original html is
    returned unchanged and extraction proceeds as before.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return html

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return html

    # Any element in a narrow sidebar column, or explicitly marked as a
    # widget, is chrome shared across pages -- never the page's own body.
    # "ctc_g_" is the WhatsApp click-to-chat popup plugin's own class
    # prefix on this site; it floats on every page and is not content
    # either, but it lives outside any "widget"-classed wrapper so the
    # selector above misses it.
    for tag in soup.select(
        '[class*="column-narrow"], [class*="widget"], [class*="ctc_g_"]'
    ):
        tag.decompose()

    return str(soup)


def _fallback_extract(html: str) -> str | None:
    """BeautifulSoup fallback: strip chrome, keep headings and paragraphs."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.find("body") or soup
    lines: list[str] = []
    for element in main.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th"]):
        text = element.get_text(" ", strip=True)
        if not text:
            continue
        name = element.name
        if name.startswith("h") and len(name) == 2 and name[1].isdigit():
            lines.append(f"\n{'#' * int(name[1])} {text}\n")
        elif name == "li":
            lines.append(f"- {text}")
        else:
            lines.append(text)

    joined = "\n".join(lines).strip()
    return _tidy(joined) if joined else None


def _extract_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not match:
        match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if not match:
        return None
    title = re.sub(r"<[^>]+>", "", match.group(1))

    # Unescape BEFORE the suffix strip. WordPress writes the separator as the
    # entity &#8211;, so a title left escaped reads "Accreditation &#8211; PCE"
    # in every citation AND never matches the separator below — meaning every
    # title also kept the site name. One missing call, two visible defects.
    title = html_module.unescape(title)
    title = re.sub(r"\s+", " ", title).strip()

    # WordPress appends " – Site Name" to every title; it adds nothing.
    for separator in (" – ", " — ", " | ", " - ", " · "):
        if separator in title:
            head = title.split(separator)[0].strip()
            if len(head) >= 3:
                title = head
                break
    return title or None


def _extract_date(html: str) -> str | None:
    for pattern in (
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)',
        r'<time[^>]+datetime=["\']([^"\']+)',
    ):
        match = re.search(pattern, html, re.I)
        if match:
            return match.group(1)[:10]
    match = _DATE_RE.search(html)
    if match:
        year, month, day = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return None


def _title_from_url(url: str) -> str:
    from urllib.parse import urlparse

    segment = (urlparse(url).path or "").strip("/").split("/")[-1]
    return segment.replace("-", " ").replace("_", " ").title() or "Untitled page"


def _doc_id_for(url: str) -> str:
    from urllib.parse import urlparse

    parts = urlparse(url)
    host = parts.netloc.replace("www.", "").split(".")[0]
    path = (parts.path or "/").strip("/").replace("/", "-") or "home"
    return f"{host}-{slugify(path)}"


def _tidy(markdown: str) -> str:
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)
    return markdown.strip()


__all__ = ["MIN_USEFUL_CHARS", "DocumentCategory", "parse_html"]
