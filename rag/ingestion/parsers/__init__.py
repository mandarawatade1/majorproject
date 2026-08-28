"""Format-specific parsers. Each returns a ParsedDocument or None."""

from rag.ingestion.parsers.html import parse_html
from rag.ingestion.parsers.markdown import DemoFrontMatterError, parse_demo_markdown
from rag.ingestion.parsers.pdf import parse_pdf
from rag.ingestion.parsers.sections import sections_from_markdown

__all__ = [
    "DemoFrontMatterError",
    "parse_demo_markdown",
    "parse_html",
    "parse_pdf",
    "sections_from_markdown",
]
