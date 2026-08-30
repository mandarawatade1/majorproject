"""Manifest arithmetic backs the 80/20 claim, so it is worth testing directly
rather than eyeballing the CLI output."""

from rag.ingestion.manifest import (
    MIN_REAL_SHARE,
    build_manifest,
    compute_stats,
    format_stats,
)
from rag.ingestion.models import DocumentCategory, ParsedDocument, Section, SourceType


def _real(index: int, words: int = 100) -> ParsedDocument:
    return ParsedDocument(
        doc_id=f"real-{index}",
        title=f"Real {index}",
        source_type=SourceType.WEB_HTML,
        category=DocumentCategory.PROGRAMME,
        text="word " * words,
        source_url=f"https://www.pce.ac.in/page-{index}",
        department="Computer Engineering",
    )


def _demo(index: int, words: int = 100) -> ParsedDocument:
    return ParsedDocument(
        doc_id=f"demo-{index}",
        title=f"Demo {index}",
        source_type=SourceType.LOCAL_MARKDOWN,
        category=DocumentCategory.SOP,
        text="word " * words,
        local_path=f"corpus/demo/demo-{index}.md",
        is_demo=True,
        demo_reason="Internal procedures are not published publicly.",
    )


class TestRatios:
    def test_exact_eighty_twenty(self) -> None:
        stats = compute_stats(
            [_real(i) for i in range(80)] + [_demo(i) for i in range(20)]
        )
        assert stats.demo_share_by_document == 0.20
        assert stats.meets_target

    def test_word_share_differs_from_document_share(self) -> None:
        """Ten short notices and ten long manuals are not equal contributions.
        Reporting only document count would hide that."""
        documents = [_real(i, words=50) for i in range(10)] + [
            _demo(i, words=500) for i in range(10)
        ]
        stats = compute_stats(documents)
        assert stats.demo_share_by_document == 0.5
        assert stats.demo_share_by_word > 0.85

    def test_a_mostly_real_corpus_passes(self) -> None:
        """The gate is one-sided, and that is the point.

        `MIN_REAL_SHARE` is a floor on real data, not a band around 80/20.
        A corpus that is 99% real exceeds the project's own commitment; failing
        it would be an instruction to fabricate demo documents to hit a ratio,
        which is the opposite of what the ratio exists to protect.
        """
        stats = compute_stats([_real(i) for i in range(99)] + [_demo(0)])
        assert stats.real_share_by_document > MIN_REAL_SHARE
        assert stats.meets_target

    def test_too_little_real_data_fails(self) -> None:
        stats = compute_stats(
            [_real(i) for i in range(50)] + [_demo(i) for i in range(50)]
        )
        assert not stats.meets_target

    def test_empty_corpus_does_not_divide_by_zero(self) -> None:
        stats = compute_stats([])
        assert stats.demo_share_by_document == 0.0
        assert stats.demo_share_by_word == 0.0


class TestBreakdowns:
    def test_counts_and_groupings(self) -> None:
        stats = compute_stats([_real(0), _real(1), _demo(0)])
        assert stats.total_documents == 3
        assert stats.real_documents == 2
        assert stats.demo_documents == 1
        assert stats.by_category["programme"] == 2
        assert stats.by_category["sop"] == 1
        assert stats.by_department["Computer Engineering"] == 2

    def test_page_provenance_is_counted(self) -> None:
        with_pages = _real(0)
        with_pages.sections = [
            Section(
                heading="A",
                level=1,
                content="x",
                order_index=0,
                start_page=1,
                end_page=2,
            )
        ]
        stats = compute_stats([with_pages, _real(1)])
        assert stats.documents_with_page_provenance == 1


class TestManifest:
    def test_every_document_carries_provenance(self) -> None:
        manifest = build_manifest([_real(0), _demo(0)])
        for row in manifest["documents"]:
            assert row["source_url"] or row["local_path"]
            assert row["content_hash"]
            assert row["fetched_at"]

    def test_demo_rows_carry_a_reason(self) -> None:
        manifest = build_manifest([_real(0), _demo(0)])
        for row in manifest["documents"]:
            if row["is_demo"]:
                assert row["demo_reason"]

    def test_real_documents_sort_before_demo(self) -> None:
        manifest = build_manifest([_demo(0), _real(0)])
        assert [r["is_demo"] for r in manifest["documents"]] == [False, True]

    def test_statistics_are_embedded(self) -> None:
        manifest = build_manifest(
            [_real(i) for i in range(8)] + [_demo(i) for i in range(2)]
        )
        assert manifest["statistics"]["min_real_share"] == MIN_REAL_SHARE
        assert manifest["statistics"]["meets_target"] is True


def test_format_stats_is_printable() -> None:
    output = format_stats(compute_stats([_real(0), _demo(0)]))
    assert "Real vs demo" in output
    assert "of documents" in output
    assert "floor met" in output
