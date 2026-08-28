"""Normalisation: what reaches disk, and what must never silently not.

`doc_id -> file_stem` is a lossy transformation — slugify truncates at 80
characters. Two consequences have already caused real data loss in this
project, and both are pinned here:

1. A consumer that re-derives the stem without the truncation looks for a
   filename that does not exist. The seed loader did this and silently skipped
   all 27 documents whose doc_id exceeded 80 characters.
2. Two long ids sharing an 80-character prefix map to one file, and the second
   overwrites the first. The manifest would list both while only one existed.
"""

from pathlib import Path

from rag.ingestion.models import DocumentCategory, ParsedDocument, SourceType, slugify
from rag.ingestion.normalise import normalise


def _doc(
    doc_id: str, text: str = "Some institutional content, long enough."
) -> ParsedDocument:
    return ParsedDocument(
        doc_id=doc_id,
        title=doc_id[:60],
        source_type=SourceType.WEB_HTML,
        category=DocumentCategory.PROGRAMME,
        text=text,
        source_url=f"https://www.pce.ac.in/{doc_id}",
    )


class TestFileStemIsTheOnlyDerivation:
    def test_a_long_doc_id_is_truncated(self) -> None:
        doc_id = "pce-" + "a" * 100
        document = _doc(doc_id)
        assert len(document.doc_id) == 104
        assert len(document.file_stem) == 80

    def test_the_file_written_matches_file_stem(self, tmp_path: Path) -> None:
        """The property and the filename must never disagree."""
        document = _doc(
            "pce-pdf-naac-approved-national-webinar-on-assessment-and-"
            "accreditation-process-of-naac"
        )
        normalise([document], tmp_path)
        assert (tmp_path / f"{document.file_stem}.json").exists()
        assert (tmp_path / f"{document.file_stem}.md").exists()

    def test_naive_rederivation_finds_nothing(self, tmp_path: Path) -> None:
        """Documents the exact defect: recomputing the stem WITHOUT the
        truncation produces a name that is not on disk."""
        import re

        document = _doc("pce-" + "b" * 90)
        normalise([document], tmp_path)

        naive = re.sub(
            r"[^a-z0-9]+", "-", document.doc_id.replace("/", "-").lower()
        ).strip("-")
        assert not (tmp_path / f"{naive}.json").exists()
        assert (tmp_path / f"{document.file_stem}.json").exists()

    def test_the_shared_slugify_reproduces_file_stem(self) -> None:
        """The documented fallback for older manifests must agree exactly."""
        for doc_id in (
            "pce-about",
            "DEMO/EXAM/2026/03",
            "pce-" + "c" * 120,
            "pce-pdf-annual-report-for-a-y-2023-24",
        ):
            document = _doc(doc_id)
            assert slugify(doc_id.replace("/", "-")) == document.file_stem


class TestStemCollisionsAreRefused:
    def test_two_long_ids_sharing_a_prefix_are_detected(self, tmp_path: Path) -> None:
        prefix = "pce-" + "d" * 78
        first, second = (
            _doc(prefix + "-one", "content one"),
            _doc(prefix + "-two", "content two"),
        )
        assert first.file_stem == second.file_stem

        result = normalise([first, second], tmp_path)
        assert len(result.collisions) == 1
        stem, a, b = result.collisions[0]
        assert stem == first.file_stem
        assert {a, b} == {first.doc_id, second.doc_id}

    def test_nothing_is_written_when_a_collision_exists(self, tmp_path: Path) -> None:
        """Writing would destroy one of the pair, so the whole run stops."""
        prefix = "pce-" + "e" * 78
        result = normalise(
            [_doc(prefix + "-x", "x"), _doc(prefix + "-y", "y")], tmp_path
        )

        assert result.written == []
        assert list(tmp_path.glob("*.json")) == []

    def test_distinct_stems_write_normally(self, tmp_path: Path) -> None:
        result = normalise([_doc("pce-a", "one"), _doc("pce-b", "two")], tmp_path)
        assert result.collisions == []
        assert len(result.written) == 2

    def test_the_same_document_twice_is_not_a_collision(self, tmp_path: Path) -> None:
        document = _doc("pce-a")
        result = normalise([document, document], tmp_path)
        assert result.collisions == []
