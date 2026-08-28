"""Crawler behaviour that can be checked without touching the network.

The politeness guarantees matter here: this code points at a real institution's
live website."""

from pathlib import Path

from rag.ingestion.crawler import CrawlConfig, Crawler, _normalise_url


class _NoRobots:
    """Stand-in policy so tests never fetch robots.txt."""

    def can_fetch(self, _url: str) -> bool:
        return True

    def delay_for(self, _url: str) -> float:
        return 0.0

    def sitemaps_for(self, _url: str) -> list[str]:
        return []


def _crawler(tmp_path: Path, **overrides: object) -> Crawler:
    config = CrawlConfig(
        base_urls=["https://www.pce.ac.in", "https://admissions.pce.ac.in"],
        output_dir=tmp_path,
        user_agent="test-agent",
        delay_seconds=0.0,
        **overrides,  # type: ignore[arg-type]
    )
    return Crawler(config, robots=_NoRobots())


class TestUrlNormalisation:
    def test_fragments_are_stripped(self) -> None:
        assert _normalise_url("https://a.test/page#section") == "https://a.test/page"

    def test_trailing_slash_is_removed(self) -> None:
        assert _normalise_url("https://a.test/page/") == "https://a.test/page"

    def test_the_two_spellings_of_one_page_collapse(self) -> None:
        assert _normalise_url("https://a.test/p/") == _normalise_url("https://a.test/p#x")

    def test_query_strings_are_preserved(self) -> None:
        assert _normalise_url("https://a.test/s?q=1") == "https://a.test/s?q=1"

    def test_non_http_schemes_are_dropped(self) -> None:
        assert _normalise_url("mailto:someone@pce.ac.in") == ""
        assert _normalise_url("javascript:void(0)") == ""

    def test_root_survives(self) -> None:
        assert _normalise_url("https://a.test/") == "https://a.test/"


class TestFrontier:
    def test_offsite_urls_are_refused(self, tmp_path: Path) -> None:
        """The crawler must never wander off the two allowed hosts."""
        with _crawler(tmp_path) as crawler:
            assert not crawler._enqueue("https://example.com/page")
            assert not crawler._enqueue("https://google.com")

    def test_allowed_hosts_are_accepted(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            assert crawler._enqueue("https://www.pce.ac.in/about")
            assert crawler._enqueue("https://admissions.pce.ac.in/faq")

    def test_a_url_is_only_queued_once(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            assert crawler._enqueue("https://www.pce.ac.in/about")
            assert not crawler._enqueue("https://www.pce.ac.in/about/")
            assert not crawler._enqueue("https://www.pce.ac.in/about#top")

    def test_skip_patterns_are_applied_and_counted(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            assert not crawler._enqueue("https://www.pce.ac.in/wp-admin/x")
            assert crawler.stats.skipped == 1


class TestCache:
    def test_paths_are_deterministic(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            first = crawler._paths_for("https://www.pce.ac.in/about/the-institute")
            second = crawler._paths_for("https://www.pce.ac.in/about/the-institute")
            assert first == second

    def test_pdfs_and_pages_get_different_suffixes(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            html_path, _ = crawler._paths_for("https://www.pce.ac.in/about")
            pdf_path, _ = crawler._paths_for("https://www.pce.ac.in/report.pdf")
            assert html_path.suffix == ".html"
            assert pdf_path.suffix == ".pdf"

    def test_cache_miss_returns_none(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            assert crawler._cached("https://www.pce.ac.in/never-fetched") is None

    def test_files_are_written_per_host(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            path, _ = crawler._paths_for("https://admissions.pce.ac.in/faq")
            assert "admissions.pce.ac.in" in str(path)


class TestConfig:
    def test_allowed_hosts_derive_from_base_urls(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            assert crawler.config.allowed_hosts == {"www.pce.ac.in", "admissions.pce.ac.in"}

    def test_defaults_are_polite(self, tmp_path: Path) -> None:
        config = CrawlConfig(
            base_urls=["https://www.pce.ac.in"], output_dir=tmp_path, user_agent="x"
        )
        assert config.delay_seconds >= 1.0
        assert config.respect_robots is True
        assert config.max_pages <= 1000


class TestBodyPathRoundTrip:
    """The crawler writes a body file and the parser must find it again.

    A PDF URL slug already ends in ".pdf", so the cached file is
    "<slug>.pdf.pdf". Reconstructing that name with Path.with_suffix(".pdf")
    yields "<slug>.pdf", which does not exist — and every PDF in the corpus was
    skipped without a word. These tests pin the round trip in both directions.
    """

    def test_pdf_body_and_sidecar_agree(self, tmp_path: Path) -> None:
        url = "https://www.pce.ac.in/wp-content/uploads/2025/02/Annual-Report.pdf"
        with _crawler(tmp_path) as crawler:
            body_path, meta_path = crawler._paths_for(url)

        stem = meta_path.name.removesuffix(".meta.json")
        assert meta_path.with_name(f"{stem}.pdf") == body_path

    def test_html_body_and_sidecar_agree(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            body_path, meta_path = crawler._paths_for("https://www.pce.ac.in/about/the-institute")

        stem = meta_path.name.removesuffix(".meta.json")
        assert meta_path.with_name(f"{stem}.html") == body_path

    def test_with_suffix_is_the_wrong_tool_here(self, tmp_path: Path) -> None:
        """Documents the exact defect, so nobody reintroduces it."""
        with _crawler(tmp_path) as crawler:
            body_path, meta_path = crawler._paths_for(
                "https://www.pce.ac.in/uploads/Annual-Report.pdf"
            )

        stem = meta_path.name.removesuffix(".meta.json")
        wrong = Path(stem).with_suffix(".pdf")
        assert wrong.name != body_path.name

    def test_sidecar_records_the_body_path(self, tmp_path: Path) -> None:
        """Belt and braces: new crawls state the path rather than implying it."""
        import json as _json

        import httpx as _httpx

        url = "https://www.pce.ac.in/uploads/Report.pdf"
        response = _httpx.Response(
            200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.4 x"
        )
        response.request = _httpx.Request("GET", url)

        with _crawler(tmp_path) as crawler:
            written = crawler._write(url, b"%PDF-1.4 x", "application/pdf", response)
            _, meta_path = crawler._paths_for(url)

        meta = _json.loads(meta_path.read_text())
        assert meta["local_path"] == str(written)
        assert Path(meta["local_path"]).exists()


class TestCacheDeterminism:
    """Cache filenames must be stable across processes.

    _paths_for once derived the filename for a query-string URL with Python's
    hash(), which is randomised per process. The same URL therefore got a
    different filename on every run, the cache never hit, and the institution's
    site was re-fetched in full each time. For a crawler pointed at someone
    else's server that is a politeness defect, not just a performance one.
    """

    def test_query_urls_hash_stably(self, tmp_path: Path) -> None:
        import hashlib

        url = "https://www.pce.ac.in/?p=2075"
        with _crawler(tmp_path) as crawler:
            body_path, _ = crawler._paths_for(url)

        expected = hashlib.sha1(b"p=2075").hexdigest()[:8]
        assert expected in body_path.name

    def test_the_same_url_maps_to_the_same_file_twice(self, tmp_path: Path) -> None:
        url = "https://www.pce.ac.in/?p=2075"
        with _crawler(tmp_path) as a, _crawler(tmp_path) as b:
            assert a._paths_for(url) == b._paths_for(url)

    def test_different_queries_map_to_different_files(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            first, _ = crawler._paths_for("https://www.pce.ac.in/?p=1")
            second, _ = crawler._paths_for("https://www.pce.ac.in/?p=2")
        assert first != second


class TestEnqueueReturnsNormalised:
    """The frontier must carry the normalised URL, not the raw one.

    _enqueue previously normalised only for the dedup set and returned a bool,
    so the caller queued the raw string. Four URLs kept their #fragment all the
    way into the fetch and into the recorded provenance.
    """

    def test_the_fragment_is_gone_from_what_is_queued(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            accepted = crawler._enqueue("https://www.pce.ac.in/uploads/brochure.pdf#new_tab")
        assert accepted == "https://www.pce.ac.in/uploads/brochure.pdf"

    def test_a_trailing_slash_is_gone_too(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            assert crawler._enqueue("https://www.pce.ac.in/about/") == (
                "https://www.pce.ac.in/about"
            )

    def test_rejection_returns_none(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            assert crawler._enqueue("https://example.com/off-site") is None
            assert crawler._enqueue("https://www.pce.ac.in/wp-admin/x") is None

    def test_two_spellings_of_one_page_are_queued_once(self, tmp_path: Path) -> None:
        with _crawler(tmp_path) as crawler:
            assert crawler._enqueue("https://www.pce.ac.in/x.pdf#a")
            assert crawler._enqueue("https://www.pce.ac.in/x.pdf#b") is None
