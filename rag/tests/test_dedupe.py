"""Deduplication.

The first real crawl produced 97 redundant documents out of 823 — 19 groups of
identical extracted text, the largest being 68 hub pages whose only substantive
block was the same shared table. These tests pin the behaviour that removes
them, and the behaviour that keeps the removal auditable.
"""

from pathlib import Path

from rag.ingestion.dedupe import deduplicate, format_report
from rag.ingestion.models import DocumentCategory, ParsedDocument, SourceType

SHARED = "The department offers a four year Bachelor of Technology programme."


def _page(doc_id: str, url: str, text: str = SHARED, **kw: object) -> ParsedDocument:
    return ParsedDocument(
        doc_id=doc_id,
        title=doc_id,
        source_type=SourceType.WEB_HTML,
        category=DocumentCategory.PROGRAMME,
        text=text,
        source_url=url,
        **kw,  # type: ignore[arg-type]
    )


class TestSuppression:
    def test_identical_text_collapses_to_one(self) -> None:
        docs = [
            _page("a", "https://www.pce.ac.in/accreditation"),
            _page("b", "https://www.pce.ac.in/accreditation/nba"),
            _page("c", "https://www.pce.ac.in/iqac/annual-reports"),
        ]
        kept, suppressed = deduplicate(docs)
        assert len(kept) == 1
        assert len(suppressed) == 2

    def test_distinct_text_is_untouched(self) -> None:
        docs = [
            _page("a", "https://www.pce.ac.in/x", text="Intake for Computer Engineering is 180."),
            _page("b", "https://www.pce.ac.in/y", text="The library subscribes to IEEE Xplore."),
        ]
        kept, suppressed = deduplicate(docs)
        assert len(kept) == 2
        assert suppressed == []

    def test_whitespace_and_case_differences_still_count_as_duplicates(self) -> None:
        """content_hash normalises before hashing, so a reflowed page is not a
        different page."""
        docs = [
            _page("a", "https://www.pce.ac.in/x", text="Hello   World\n"),
            _page("b", "https://www.pce.ac.in/y", text="hello world"),
        ]
        kept, _ = deduplicate(docs)
        assert len(kept) == 1

    def test_empty_input(self) -> None:
        assert deduplicate([]) == ([], [])


class TestWhichSurvives:
    def test_the_shallower_url_wins(self) -> None:
        docs = [
            _page("deep", "https://www.pce.ac.in/accreditation/nba/reports/2024"),
            _page("shallow", "https://www.pce.ac.in/accreditation"),
        ]
        kept, suppressed = deduplicate(docs)
        assert kept[0].doc_id == "shallow"
        assert suppressed[0].doc_id == "deep"

    def test_a_real_document_beats_a_demo_one(self) -> None:
        real = _page("real", "https://www.pce.ac.in/a/b/c/d/e")
        demo = ParsedDocument(
            doc_id="demo",
            title="demo",
            source_type=SourceType.LOCAL_MARKDOWN,
            category=DocumentCategory.SOP,
            text=SHARED,
            local_path="corpus/demo/x.md",
            is_demo=True,
            demo_reason="Internal procedures are not published publicly.",
        )
        kept, suppressed = deduplicate([demo, real])
        assert kept[0].doc_id == "real"
        assert suppressed[0].doc_id == "demo"

    def test_the_choice_is_deterministic(self) -> None:
        """Two runs over the same corpus must keep the same document, or the
        manifest churns on every parse."""
        docs = [
            _page("b", "https://www.pce.ac.in/page-b"),
            _page("a", "https://www.pce.ac.in/page-a"),
            _page("c", "https://www.pce.ac.in/page-c"),
        ]
        first = deduplicate(list(docs))[0][0].doc_id
        second = deduplicate(list(reversed(docs)))[0][0].doc_id
        assert first == second

    def test_kept_documents_hold_their_input_order(self) -> None:
        docs = [
            _page("a", "https://www.pce.ac.in/a", text="one"),
            _page("b", "https://www.pce.ac.in/b", text="two"),
            _page("c", "https://www.pce.ac.in/c", text="three"),
        ]
        kept, _ = deduplicate(docs)
        assert [d.doc_id for d in kept] == ["a", "b", "c"]


class TestAuditability:
    def test_a_suppression_records_what_it_duplicated(self) -> None:
        docs = [
            _page("kept", "https://www.pce.ac.in/x"),
            _page("dropped", "https://www.pce.ac.in/x/y/z"),
        ]
        _, suppressed = deduplicate(docs)
        entry = suppressed[0]
        assert entry.duplicate_of == "kept"
        assert entry.source_url == "https://www.pce.ac.in/x/y/z"
        assert entry.content_hash

    def test_the_dropped_url_survives_into_the_manifest_row(self) -> None:
        """A suppressed page must still be answerable as 'yes, we crawled it'."""
        docs = [
            _page("kept", "https://www.pce.ac.in/x"),
            _page("dropped", "https://www.pce.ac.in/x/y"),
        ]
        _, suppressed = deduplicate(docs)
        row = suppressed[0].to_dict()
        assert row["source_url"] == "https://www.pce.ac.in/x/y"
        assert row["duplicate_of"] == "kept"


class TestReport:
    def test_reports_nothing_when_there_is_nothing(self) -> None:
        assert "no duplicate content" in format_report([], 10)

    def test_summarises_the_worst_groups(self) -> None:
        docs = [_page(f"d{i}", f"https://www.pce.ac.in/{'x/' * i}p") for i in range(6)]
        _, suppressed = deduplicate(docs)
        report = format_report(suppressed, len(docs))
        assert "suppressed 5 of 6" in report
        assert "copies -> kept" in report


class TestPruningIsWhatMakesDedupeReal:
    """Deduplication that does not reach the disk is not deduplication.

    normalise() once only ever added files, so a suppressed document kept its
    output forever and load_documents() read it straight back. The first
    deduplicating run suppressed 214 documents and 200 survived on disk; the
    manifest then reported a corpus still containing every duplicate. These
    tests exist so that cannot recur silently.
    """

    def test_a_suppressed_document_leaves_no_file_behind(self, tmp_path: Path) -> None:
        from rag.ingestion.normalise import normalise

        docs = [
            _page("kept", "https://www.pce.ac.in/x"),
            _page("dropped", "https://www.pce.ac.in/x/y/z"),
        ]
        normalise(docs, tmp_path)
        assert (tmp_path / "dropped.json").exists()

        kept, suppressed = deduplicate(docs)
        normalise(kept, tmp_path)

        assert suppressed[0].doc_id == "dropped"
        assert not (tmp_path / "dropped.json").exists()
        assert not (tmp_path / "dropped.md").exists()
        assert (tmp_path / "kept.json").exists()

    def test_the_directory_matches_the_kept_set_exactly(self, tmp_path: Path) -> None:
        from rag.ingestion.normalise import normalise

        first = [_page(f"d{i}", f"https://www.pce.ac.in/p{i}", text=f"body {i}") for i in range(5)]
        normalise(first, tmp_path)
        assert len(list(tmp_path.glob("*.json"))) == 5

        second = first[:2]
        result = normalise(second, tmp_path)

        assert len(list(tmp_path.glob("*.json"))) == 2
        assert len(result.pruned) == 6  # three .json and three .md

    def test_an_empty_parse_does_not_wipe_the_corpus(self, tmp_path: Path) -> None:
        """A failed parse must not delete a good corpus on the strength of
        having produced nothing."""
        from rag.ingestion.normalise import normalise

        normalise([_page("a", "https://www.pce.ac.in/a")], tmp_path)
        result = normalise([], tmp_path)

        assert result.pruned == []
        assert (tmp_path / "a.json").exists()

    def test_pruning_can_be_turned_off(self, tmp_path: Path) -> None:
        from rag.ingestion.normalise import normalise

        normalise([_page("a", "https://www.pce.ac.in/a", text="one")], tmp_path)
        normalise([_page("b", "https://www.pce.ac.in/b", text="two")], tmp_path, prune=False)
        assert (tmp_path / "a.json").exists()
        assert (tmp_path / "b.json").exists()

    def test_unrelated_files_are_left_alone(self, tmp_path: Path) -> None:
        from rag.ingestion.normalise import normalise

        (tmp_path / "notes.txt").write_text("not a corpus artefact")
        normalise([_page("a", "https://www.pce.ac.in/a")], tmp_path)
        assert (tmp_path / "notes.txt").exists()
