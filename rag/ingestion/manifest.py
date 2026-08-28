"""The corpus manifest: one file that answers "what is in the corpus, and
where did each piece come from?"

corpus/manifest.json is the contract between Phase 1 and everything after it.
Phase 2 loads it into PostgreSQL; the admin console reads its statistics; the
report quotes its real-versus-demo ratio. Because it records provenance for
every document, any claim the finished system makes can be walked back to a
URL and a fetch timestamp.

The ratio is reported two ways. By **document count**, because that is the
target stated in the plan. By **word count**, because ten one-paragraph notices
and ten forty-page reports are not the same contribution to a corpus, and a
count-only figure can be quietly misleading.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rag.ingestion.models import ParsedDocument

MANIFEST_VERSION = 1

MIN_REAL_SHARE = 0.80
"""The corpus must be at least this proportion real institutional data.

This is a FLOOR, not a band. The project brief asks for "~80% real, ~20%
clearly labelled demo", and the intent of that is a guarantee about how much of
what the system knows is genuine. A corpus that is 97% real over-delivers on
that guarantee; it is not a defect, and an earlier two-sided check that
reported it as one was wrong.

Demo share is still reported, because it answers a different and useful
question: is there enough internal-document coverage to evaluate that retrieval
path? That question is answered by counting golden-set questions, not by a
percentage, so it is reported for information rather than enforced.
"""


@dataclass
class CorpusStats:
    total_documents: int
    real_documents: int
    demo_documents: int
    total_words: int
    real_words: int
    demo_words: int
    by_category: dict[str, int]
    by_source_type: dict[str, int]
    by_department: dict[str, int]
    documents_with_page_provenance: int
    total_sections: int
    duplicates_suppressed: int = 0

    @property
    def demo_share_by_document(self) -> float:
        return self.demo_documents / self.total_documents if self.total_documents else 0.0

    @property
    def demo_share_by_word(self) -> float:
        return self.demo_words / self.total_words if self.total_words else 0.0

    @property
    def real_share_by_document(self) -> float:
        return self.real_documents / self.total_documents if self.total_documents else 0.0

    @property
    def meets_target(self) -> bool:
        """True when at least MIN_REAL_SHARE of the corpus is real data."""
        return self.real_share_by_document >= MIN_REAL_SHARE

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_documents": self.total_documents,
            "real_documents": self.real_documents,
            "demo_documents": self.demo_documents,
            "real_share_by_document": round(self.real_share_by_document, 4),
            "demo_share_by_document": round(self.demo_share_by_document, 4),
            "demo_share_by_word": round(self.demo_share_by_word, 4),
            "min_real_share": MIN_REAL_SHARE,
            "meets_target": self.meets_target,
            "total_words": self.total_words,
            "real_words": self.real_words,
            "demo_words": self.demo_words,
            "total_sections": self.total_sections,
            "duplicates_suppressed": self.duplicates_suppressed,
            "documents_with_page_provenance": self.documents_with_page_provenance,
            "by_category": self.by_category,
            "by_source_type": self.by_source_type,
            "by_department": self.by_department,
        }


def compute_stats(documents: list[ParsedDocument], duplicates_suppressed: int = 0) -> CorpusStats:
    real = [d for d in documents if not d.is_demo]
    demo = [d for d in documents if d.is_demo]

    return CorpusStats(
        total_documents=len(documents),
        real_documents=len(real),
        demo_documents=len(demo),
        total_words=sum(d.word_count for d in documents),
        real_words=sum(d.word_count for d in real),
        demo_words=sum(d.word_count for d in demo),
        by_category=dict(Counter(d.category.value for d in documents).most_common()),
        by_source_type=dict(Counter(d.source_type.value for d in documents).most_common()),
        by_department=dict(Counter(d.department for d in documents if d.department).most_common()),
        documents_with_page_provenance=sum(
            1 for d in documents if any(s.start_page is not None for s in d.sections)
        ),
        total_sections=sum(len(d.sections) for d in documents),
        duplicates_suppressed=duplicates_suppressed,
    )


def build_manifest(
    documents: list[ParsedDocument],
    suppressed: list[Any] | None = None,
) -> dict[str, Any]:
    """The manifest: statistics, a provenance row per document, and a
    record of every document suppressed as a duplicate.

    Suppressed documents are listed rather than forgotten, so the corpus
    can still answer "was this page crawled?" with a yes and a pointer to
    the document that carries its content.
    """
    suppressed = suppressed or []
    return {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "statistics": compute_stats(documents, len(suppressed)).to_dict(),
        "suppressed_duplicates": [
            item.to_dict() if hasattr(item, "to_dict") else item for item in suppressed
        ],
        "documents": [
            {
                "doc_id": d.doc_id,
                "title": d.title,
                "category": d.category.value,
                "source_type": d.source_type.value,
                "source_url": d.source_url,
                "local_path": d.local_path,
                "fetched_at": d.fetched_at,
                "content_hash": d.content_hash,
                "department": d.department,
                "published_date": d.published_date,
                "page_count": d.page_count,
                "word_count": d.word_count,
                "section_count": len(d.sections),
                "has_page_provenance": any(s.start_page is not None for s in d.sections),
                "is_demo": d.is_demo,
                "demo_reason": d.demo_reason,
            }
            for d in sorted(documents, key=lambda x: (x.is_demo, x.category.value, x.doc_id))
        ],
    }


def write_manifest(
    documents: list[ParsedDocument],
    path: Path,
    suppressed: list[Any] | None = None,
) -> dict[str, Any]:
    manifest = build_manifest(documents, suppressed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def load_documents(normalised_dir: Path) -> list[ParsedDocument]:
    """Rebuild ParsedDocuments from corpus/normalised/*.json."""
    from rag.ingestion.models import DocumentCategory, Section, SourceType

    documents: list[ParsedDocument] = []
    for path in sorted(normalised_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sections = [Section(**s) for s in raw.pop("sections", [])]
        raw["source_type"] = SourceType(raw["source_type"])
        raw["category"] = DocumentCategory(raw["category"])
        documents.append(ParsedDocument(sections=sections, **raw))
    return documents


def format_stats(stats: CorpusStats) -> str:
    """A readable summary for the CLI and for pasting into the report."""
    lines = [
        "Corpus statistics",
        "=================",
        f"  documents          {stats.total_documents}",
        f"    real             {stats.real_documents}",
        f"    demo             {stats.demo_documents}",
        f"  sections           {stats.total_sections}",
        f"  duplicates dropped {stats.duplicates_suppressed}",
        f"  words              {stats.total_words:,}",
        f"  page provenance    {stats.documents_with_page_provenance} documents "
        f"(PDFs carry page numbers; HTML has no pages)",
        "",
        "Real vs demo",
        "------------",
        f"  real               {stats.real_share_by_document:.1%} of documents "
        f"(floor: {MIN_REAL_SHARE:.0%})",
        f"  demo               {stats.demo_share_by_document:.1%} of documents, "
        f"{stats.demo_share_by_word:.1%} of words",
        f"  floor met          {'YES' if stats.meets_target else 'NO'}",
    ]

    if stats.by_category:
        lines += ["", "By category", "-----------"]
        width = max(len(k) for k in stats.by_category)
        lines += [f"  {k:<{width}}  {v}" for k, v in stats.by_category.items()]

    if stats.by_department:
        lines += ["", "By department", "-------------"]
        width = max(len(k) for k in stats.by_department)
        lines += [f"  {k:<{width}}  {v}" for k, v in stats.by_department.items()]

    if stats.by_source_type:
        lines += ["", "By source type", "--------------"]
        width = max(len(k) for k in stats.by_source_type)
        lines += [f"  {k:<{width}}  {v}" for k, v in stats.by_source_type.items()]

    return "\n".join(lines)
