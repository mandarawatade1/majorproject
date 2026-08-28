"""The categoriser decides what gets filtered at retrieval time, so its rules
are worth pinning down explicitly."""

import pytest

from rag.ingestion.categorise import (
    categorise,
    infer_department,
    is_pdf_url,
    should_skip,
)
from rag.ingestion.models import DocumentCategory


class TestCategorise:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://www.pce.ac.in/accreditation/naac/", DocumentCategory.ACCREDITATION),
            ("https://www.pce.ac.in/accreditation/nirf/", DocumentCategory.ACCREDITATION),
            (
                "https://www.pce.ac.in/bachelors/computer-engineering/curriculum/",
                DocumentCategory.CURRICULUM,
            ),
            ("https://www.pce.ac.in/academics/bachelors/", DocumentCategory.PROGRAMME),
            ("https://admissions.pce.ac.in/faq", DocumentCategory.ADMISSION),
            ("https://www.pce.ac.in/about/the-institute/", DocumentCategory.INSTITUTE_PROFILE),
            ("https://www.pce.ac.in/faculty/directory", DocumentCategory.FACULTY),
            ("https://www.pce.ac.in/library/resources", DocumentCategory.LIBRARY),
            ("https://www.pce.ac.in/research/publications", DocumentCategory.RESEARCH),
            ("https://www.pce.ac.in/students/placements", DocumentCategory.PLACEMENT),
        ],
    )
    def test_known_urls(self, url: str, expected: DocumentCategory) -> None:
        assert categorise(url) == expected

    def test_curriculum_beats_programme(self) -> None:
        """Both patterns match this URL; the more specific rule must win."""
        url = "https://www.pce.ac.in/bachelors/computer-engineering/curriculum/"
        assert categorise(url) is DocumentCategory.CURRICULUM

    def test_unknown_url_is_other(self) -> None:
        assert categorise("https://www.pce.ac.in/something-unmapped/") is DocumentCategory.OTHER


class TestInternalOnlyCategories:
    @pytest.mark.parametrize(
        "category",
        [
            DocumentCategory.INTERNAL_WIKI,
            DocumentCategory.SOP,
            DocumentCategory.CIRCULAR,
            DocumentCategory.LAB_MANUAL,
            DocumentCategory.HELPDESK,
            DocumentCategory.TIMETABLE,
        ],
    )
    def test_internal_categories_are_flagged(self, category: DocumentCategory) -> None:
        assert category.is_internal_only

    @pytest.mark.parametrize(
        "category",
        [DocumentCategory.PROGRAMME, DocumentCategory.FACULTY, DocumentCategory.REPORT],
    )
    def test_public_categories_are_not(self, category: DocumentCategory) -> None:
        assert not category.is_internal_only


class TestDepartment:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("/bachelors/computer-engineering/", "Computer Engineering"),
            ("/bachelors/information-technology/", "Information Technology"),
            ("/bachelors/automobile-engineering/", "Automobile Engineering"),
            ("/bachelors/mechanical-engineering/", "Mechanical Engineering"),
        ],
    )
    def test_from_url(self, url: str, expected: str) -> None:
        assert infer_department(url) == expected

    def test_electronics_variants_are_distinguished(self) -> None:
        """These two share a prefix; misfiling one under the other would put
        every ECS document in the EXTC filter."""
        assert (
            infer_department("/bachelors/electronics-computer-science/")
            == "Electronics and Computer Science"
        )
        assert (
            infer_department("/bachelors/electronics-and-telecommunication-engineering/")
            == "Electronics and Telecommunication Engineering"
        )

    def test_falls_back_to_text(self) -> None:
        assert (
            infer_department("/some/page", "The Department of Computer Engineering was...")
            == "Computer Engineering"
        )

    def test_ignores_department_mentioned_late_in_a_long_document(self) -> None:
        text = "x" * 5000 + " Department of Mechanical Engineering "
        assert infer_department("/annual-report", text) is None

    def test_returns_none_when_unknown(self) -> None:
        assert infer_department("/about/contact") is None


class TestSkipRules:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.pce.ac.in/wp-admin/",
            "https://www.pce.ac.in/feed/",
            "https://www.pce.ac.in/tag/news/",
            "https://www.pce.ac.in/page/4",
            "https://www.pce.ac.in/logo.png",
            "https://www.pce.ac.in/style.css",
            "https://www.pce.ac.in/post?replytocom=12",
        ],
    )
    def test_skipped(self, url: str) -> None:
        assert should_skip(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.pce.ac.in/about/the-institute/",
            "https://www.pce.ac.in/report.pdf",
        ],
    )
    def test_not_skipped(self, url: str) -> None:
        assert not should_skip(url)

    def test_docx_is_skipped_but_pdf_is_not(self) -> None:
        """PDFs are the point of the crawl; Word files are not worth parsing."""
        assert should_skip("https://www.pce.ac.in/x.docx")
        assert not should_skip("https://www.pce.ac.in/x.pdf")


def test_is_pdf_url() -> None:
    assert is_pdf_url("https://www.pce.ac.in/annual-report.pdf")
    # The query string is not part of the path, so this is still a PDF.
    assert is_pdf_url("https://www.pce.ac.in/a.PDF?download=1")
    assert not is_pdf_url("https://www.pce.ac.in/about/")


class TestStaticAssetsWithQueryStrings:
    """WordPress appends ?ver=... to every stylesheet and script. Matching the
    extension against the whole URL let all of them through the filter."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.pce.ac.in/wp-includes/css/dashicons.min.css?ver=6.9.7",
            "https://www.pce.ac.in/wp-includes/js/jquery.js?ver=3.7.1",
            "https://www.pce.ac.in/uploads/logo.png?v=2",
        ],
    )
    def test_cache_busted_assets_are_skipped(self, url: str) -> None:
        assert should_skip(url)

    def test_a_pdf_with_a_query_string_is_still_crawled(self) -> None:
        assert not should_skip("https://www.pce.ac.in/report.pdf?download=1")
