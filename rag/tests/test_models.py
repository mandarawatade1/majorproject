"""ParsedDocument.validate() is the gate that keeps unlabelled or
unprovenanced material out of the corpus. These tests are the reason to trust
the is_demo flag downstream."""

from rag.ingestion.models import (
    DocumentCategory,
    ParsedDocument,
    Section,
    SourceType,
    compute_content_hash,
    slugify,
)


def _document(**overrides: object) -> ParsedDocument:
    defaults: dict[str, object] = {
        "doc_id": "pce-about",
        "title": "About the Institute",
        "source_type": SourceType.WEB_HTML,
        "category": DocumentCategory.INSTITUTE_PROFILE,
        "text": "Established in 1999 under the Mahatma Education Society.",
        "source_url": "https://www.pce.ac.in/about/the-institute/",
    }
    defaults.update(overrides)
    return ParsedDocument(**defaults)  # type: ignore[arg-type]


class TestValidation:
    def test_a_well_formed_document_passes(self) -> None:
        assert _document().validate() == []

    def test_a_document_with_no_provenance_fails(self) -> None:
        problems = _document(source_url=None, local_path=None).validate()
        assert any("provenance" in p for p in problems)

    def test_demo_without_a_reason_fails(self) -> None:
        problems = _document(is_demo=True, category=DocumentCategory.SOP).validate()
        assert any("demo_reason" in p for p in problems)

    def test_internal_only_category_marked_real_fails(self) -> None:
        """An SOP claiming to be public data is the exact mistake that would
        make the 80/20 split meaningless."""
        problems = _document(category=DocumentCategory.SOP, is_demo=False).validate()
        assert any("internal-only" in p for p in problems)

    def test_internal_only_category_marked_demo_passes(self) -> None:
        document = _document(
            category=DocumentCategory.SOP,
            is_demo=True,
            demo_reason="Internal procedures are never published publicly.",
        )
        assert document.validate() == []

    def test_pdf_without_page_numbers_fails(self) -> None:
        """Page-level provenance is a project requirement, not a nicety."""
        document = _document(
            source_type=SourceType.WEB_PDF,
            sections=[Section(heading="A", level=1, content="x" * 60, order_index=0)],
        )
        assert any("page numbers" in p for p in document.validate())

    def test_pdf_with_page_numbers_passes(self) -> None:
        document = _document(
            source_type=SourceType.WEB_PDF,
            sections=[
                Section(
                    heading="A",
                    level=1,
                    content="x" * 60,
                    order_index=0,
                    start_page=3,
                    end_page=4,
                )
            ],
        )
        assert document.validate() == []

    def test_empty_text_fails(self) -> None:
        assert any("text is empty" in p for p in _document(text="   ").validate())


class TestDefaults:
    def test_fetched_at_and_hash_are_filled_in(self) -> None:
        document = _document()
        assert document.fetched_at
        assert len(document.content_hash) == 64

    def test_word_count(self) -> None:
        assert _document(text="one two three").word_count == 3


class TestContentHash:
    def test_is_stable(self) -> None:
        assert compute_content_hash("Hello world") == compute_content_hash("Hello world")

    def test_ignores_whitespace_and_case(self) -> None:
        """A page whose sidebar reflowed has not changed its content."""
        assert compute_content_hash("Hello   world\n") == compute_content_hash("hello world")

    def test_detects_a_real_change(self) -> None:
        assert compute_content_hash("Intake is 180") != compute_content_hash("Intake is 120")


class TestSlugify:
    def test_basic(self) -> None:
        assert slugify("About The Institute!") == "about-the-institute"

    def test_truncates_without_a_trailing_hyphen(self) -> None:
        assert not slugify("word " * 60, max_length=20).endswith("-")

    def test_empty_input_has_a_fallback(self) -> None:
        assert slugify("!!!") == "untitled"


class TestFileStem:
    """doc_id may be a real-world identifier containing slashes; the filename
    derived from it must never contain a path separator."""

    def test_slashes_do_not_become_directories(self) -> None:
        document = _document(doc_id="DEMO/EXAM/2026/03")
        assert "/" not in document.file_stem
        assert document.file_stem == "demo-exam-2026-03"

    def test_the_identifier_itself_is_untouched(self) -> None:
        document = _document(doc_id="DEMO/EXAM/2026/03")
        assert document.doc_id == "DEMO/EXAM/2026/03"

    def test_ordinary_ids_pass_through(self) -> None:
        assert _document(doc_id="pce-about-the-institute").file_stem == "pce-about-the-institute"

    def test_distinct_ids_stay_distinct(self) -> None:
        assert (
            _document(doc_id="DEMO/CE/2026/07").file_stem
            != _document(doc_id="DEMO/CE/2026/08").file_stem
        )
