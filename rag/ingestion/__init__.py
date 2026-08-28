"""Corpus ingestion: acquire, parse and normalise institutional documents.

The pipeline, in order:

    crawler.py    fetch pages and PDFs politely, cache raw bytes on disk
    parsers/      HTML -> markdown + heading tree; PDF -> text + page numbers;
                  markdown -> demo documents with mandatory front matter
    normalise.py  write corpus/normalised/<doc_id>.{md,json}
    manifest.py   corpus/manifest.json — provenance and real/demo accounting

Every document that leaves this package carries where it came from, when it was
fetched, and whether it is real or demo. Phase 2 loads the manifest into
PostgreSQL; nothing downstream ever has to guess a document's origin.
"""

from rag.ingestion.models import (
    DocumentCategory,
    ParsedDocument,
    Section,
    SourceType,
)

__all__ = ["DocumentCategory", "ParsedDocument", "Section", "SourceType"]
