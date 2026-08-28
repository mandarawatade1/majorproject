"""Suppress documents whose extracted text is identical to another's.

A WordPress site gives many hub pages the same body. On the first real crawl,
68 distinct URLs — /accreditation/, /accreditation/nba/, /iqac/ and 65 others —
produced byte-identical extracted text, because the only substantive block on
each was a shared "Departments" table. Across the corpus that was 97 redundant
documents out of 823, roughly 42,600 wasted words.

Left in, that is not merely untidy. Retrieval would return the same table five
times for a single question, filling the whole context budget with one block
and starving the answer of anything else. Context Precision — one of the three
RAGAS metrics this project reports — measures exactly that, so duplicates would
depress a headline result for a reason that has nothing to do with the
retrieval strategy being evaluated.

Suppression is recorded, never silent. Every suppressed document keeps its URL
in the manifest alongside the document it duplicates, so the corpus can still
answer "did you crawl this page?" with a yes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlparse

from rag.ingestion.models import ParsedDocument


@dataclass(slots=True)
class Suppression:
    """One document dropped as a duplicate of another."""

    doc_id: str
    title: str
    source_url: str | None
    duplicate_of: str
    content_hash: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "source_url": self.source_url,
            "duplicate_of": self.duplicate_of,
            "content_hash": self.content_hash,
        }


def deduplicate(
    documents: list[ParsedDocument],
) -> tuple[list[ParsedDocument], list[Suppression]]:
    """Return (kept, suppressed), preserving the input order of kept documents.

    Documents are grouped by `content_hash`, which is computed over normalised
    text, so two pages differing only in whitespace or casing group together.
    """
    by_hash: dict[str, list[ParsedDocument]] = defaultdict(list)
    for document in documents:
        by_hash[document.content_hash].append(document)

    keep_ids: set[str] = set()
    suppressed: list[Suppression] = []

    for group in by_hash.values():
        if len(group) == 1:
            keep_ids.add(group[0].doc_id)
            continue

        winner = _canonical(group)
        keep_ids.add(winner.doc_id)
        for document in group:
            if document.doc_id == winner.doc_id:
                continue
            suppressed.append(
                Suppression(
                    doc_id=document.doc_id,
                    title=document.title,
                    source_url=document.source_url,
                    duplicate_of=winner.doc_id,
                    content_hash=document.content_hash,
                )
            )

    kept = [d for d in documents if d.doc_id in keep_ids]
    return kept, suppressed


def _canonical(group: list[ParsedDocument]) -> ParsedDocument:
    """Pick which member of a duplicate group to keep.

    Preference order, each a tiebreak for the one above:

    1. Real over demo. A demo document should never collide with a real one,
       but if it ever did, the real document is the one to keep.
    2. Fewest URL path segments. Where /accreditation/ and /accreditation/nba/
       carry the same text, the shallower URL is the more canonical home for
       it.
    3. Shortest URL, then doc_id. Not meaningful in themselves — they make the
       choice deterministic, so two runs over the same corpus keep the same
       document and the manifest does not churn.
    """

    def sort_key(document: ParsedDocument) -> tuple[int, int, int, str]:
        url = document.source_url or document.local_path or ""
        depth = len([p for p in urlparse(url).path.split("/") if p])
        return (int(document.is_demo), depth, len(url), document.doc_id)

    return min(group, key=sort_key)


def format_report(suppressed: list[Suppression], total: int) -> str:
    """A short summary for the CLI."""
    if not suppressed:
        return "deduplication: no duplicate content found"

    groups: dict[str, list[Suppression]] = defaultdict(list)
    for item in suppressed:
        groups[item.duplicate_of].append(item)

    share = len(suppressed) / total if total else 0.0
    lines = [
        f"deduplication: suppressed {len(suppressed)} of {total} documents "
        f"({share:.1%}) across {len(groups)} duplicate group(s)",
    ]

    worst = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)[:5]
    for kept_id, items in worst:
        lines.append(f"    {len(items) + 1} copies -> kept {kept_id}")
        for item in items[:2]:
            lines.append(f"        dropped {item.source_url or item.doc_id}")
        if len(items) > 2:
            lines.append(f"        ... and {len(items) - 2} more")

    return "\n".join(lines)
