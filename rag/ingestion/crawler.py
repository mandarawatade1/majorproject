"""A deliberately polite crawler for institutional websites.

Design constraints, in priority order:

1. Be a good guest. Obey robots.txt, identify ourselves with a real contact
   address, rate-limit to roughly one request per second, and never run
   concurrent requests against the same host. Crawling a college's live site
   for a student project is a privilege, not an entitlement.
2. Crawl once. Every response is cached to corpus/raw/ with a metadata
   sidecar. Re-running the pipeline re-reads the cache and does not touch the
   network unless --refresh is passed. Development iterations should cost the
   site nothing.
3. Record provenance for everything. URL, fetch timestamp, HTTP status,
   content type and ETag are stored beside every artefact.

Single-threaded on purpose. At one request per second, concurrency buys
nothing and only risks hammering the host.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from rag.ingestion.categorise import is_pdf_url, should_skip

_LINK_RE = re.compile(r"""href\s*=\s*["']([^"'>\s]+)["']""", re.I)
_SITEMAP_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


@dataclass
class CrawlConfig:
    """Everything the crawler needs. Mirrors the CRAWL_* keys in .env."""

    base_urls: list[str]
    output_dir: Path
    user_agent: str
    delay_seconds: float = 1.0
    max_pages: int = 1000
    timeout_seconds: float = 30.0
    respect_robots: bool = True
    refresh: bool = False
    max_depth: int = 4
    # Fetch exactly the URLs given, ignoring the site's sitemap.
    #
    # `_seeds_for` expands a base URL into everything the host's sitemap
    # lists, which is right for taking a whole site and wrong for adding a
    # handful of named pages: `urljoin(base, "/sitemap.xml")` resolves to the
    # host root, so even a deep seed URL pulls the entire site. Topping up a
    # corpus with specific pages needs this off.
    only_seeds: bool = False

    @property
    def allowed_hosts(self) -> set[str]:
        """Only hosts named in base_urls are ever fetched."""
        return {urlparse(u).netloc for u in self.base_urls}


@dataclass
class CrawlResult:
    """One fetched artefact, already written to disk."""

    url: str
    local_path: Path
    content_type: str
    status_code: int
    fetched_at: str
    from_cache: bool
    depth: int


@dataclass
class CrawlStats:
    fetched: int = 0
    from_cache: int = 0
    skipped: int = 0
    disallowed: int = 0
    errors: int = 0
    discovered: int = 0
    error_urls: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"fetched={self.fetched} (cache={self.from_cache}) "
            f"skipped={self.skipped} disallowed={self.disallowed} "
            f"errors={self.errors} discovered={self.discovered}"
        )


class Crawler:
    """Breadth-first crawler, seeded from sitemaps where the site offers them."""

    def __init__(self, config: CrawlConfig, robots: object | None = None) -> None:
        self.config = config
        self.stats = CrawlStats()
        self._seen: set[str] = set()

        # Imported lazily so tests can construct a Crawler without network.
        if robots is None:
            from rag.ingestion.robots import RobotsPolicy

            robots = RobotsPolicy(
                user_agent=config.user_agent,
                default_delay=config.delay_seconds,
            )
        self.robots = robots

        self._client = httpx.Client(
            headers={"User-Agent": config.user_agent},
            timeout=config.timeout_seconds,
            follow_redirects=True,
        )

    # --- Public API -------------------------------------------------------

    def crawl(self) -> list[CrawlResult]:
        """Crawl every allowed host and return what was fetched."""
        results: list[CrawlResult] = []
        frontier: deque[tuple[str, int]] = deque()

        for base in self.config.base_urls:
            for seed in self._seeds_for(base):
                accepted = self._enqueue(seed)
                if accepted:
                    frontier.append((accepted, 0))

        while frontier and self.stats.fetched < self.config.max_pages:
            url, depth = frontier.popleft()

            result = self._fetch(url, depth)
            if result is None:
                continue
            results.append(result)

            # `only_seeds` has to stop link-following too, not just sitemap
            # expansion. It originally did only the latter, so a run seeded
            # with three URLs breadth-first-followed every link on them and
            # fetched 39 pages -- the whole university site, blogs and a font
            # file included. The flag said "only the seeds" and delivered
            # "no sitemap", which is the kind of gap that looks like success.
            if (
                self.config.only_seeds
                or depth >= self.config.max_depth
                or is_pdf_url(url)
            ):
                continue

            for link in self._links_in(result):
                accepted = self._enqueue(link)
                if accepted:
                    frontier.append((accepted, depth + 1))

        return results

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Crawler:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- Seeding ----------------------------------------------------------

    def _seeds_for(self, base: str) -> list[str]:
        """Prefer the site's own sitemap; fall back to the base URL."""
        seeds: list[str] = [base]
        if self.config.only_seeds:
            return seeds
        for sitemap_url in self._sitemap_candidates(base):
            urls = self._read_sitemap(sitemap_url)
            if urls:
                seeds.extend(urls)
                break
        return seeds

    def _sitemap_candidates(self, base: str) -> list[str]:
        declared: list[str] = []
        if self.config.respect_robots and hasattr(self.robots, "sitemaps_for"):
            declared = list(self.robots.sitemaps_for(base))
        conventional = [
            urljoin(base, "/wp-sitemap.xml"),
            urljoin(base, "/sitemap.xml"),
            urljoin(base, "/sitemap_index.xml"),
        ]
        return declared + [c for c in conventional if c not in declared]

    def _read_sitemap(self, sitemap_url: str, depth: int = 0) -> list[str]:
        """Read a sitemap, following one level of sitemap-index nesting."""
        if depth > 1:
            return []
        try:
            response = self._client.get(sitemap_url)
            if response.status_code != 200 or "xml" not in response.headers.get("content-type", ""):
                return []
        except httpx.HTTPError:
            return []

        time.sleep(self.config.delay_seconds)
        locs = _SITEMAP_LOC_RE.findall(response.text)

        if sitemap_url.endswith(("sitemap.xml", "sitemap_index.xml")) and any(
            loc.endswith(".xml") for loc in locs
        ):
            nested: list[str] = []
            for loc in locs:
                if loc.endswith(".xml"):
                    nested.extend(self._read_sitemap(loc, depth + 1))
                else:
                    nested.append(loc)
            return nested
        return [loc for loc in locs if not loc.endswith(".xml")]

    # --- Frontier ---------------------------------------------------------

    def _enqueue(self, url: str) -> str | None:
        """Normalise, deduplicate and filter.

        Returns the NORMALISED url when accepted, and None otherwise. Returning
        it matters: an earlier version normalised only for the dedup set and
        let the caller queue the raw string, so fragments survived into the
        fetch and into the recorded provenance.
        """
        normalised = _normalise_url(url)
        if not normalised or normalised in self._seen:
            return None
        if urlparse(normalised).netloc not in self.config.allowed_hosts:
            return None
        if should_skip(normalised):
            self.stats.skipped += 1
            self._seen.add(normalised)
            return None

        self._seen.add(normalised)
        self.stats.discovered += 1
        return normalised

    # --- Fetching ---------------------------------------------------------

    def _fetch(self, url: str, depth: int) -> CrawlResult | None:
        cached = self._cached(url)
        if cached is not None and not self.config.refresh:
            self.stats.from_cache += 1
            self.stats.fetched += 1
            return cached

        if self.config.respect_robots and not self.robots.can_fetch(url):  # type: ignore[attr-defined]
            self.stats.disallowed += 1
            return None

        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            self.stats.errors += 1
            self.stats.error_urls.append(f"{url} :: {type(exc).__name__}")
            return None
        finally:
            delay = (
                self.robots.delay_for(url)  # type: ignore[attr-defined]
                if self.config.respect_robots and hasattr(self.robots, "delay_for")
                else self.config.delay_seconds
            )
            time.sleep(delay)

        if response.status_code != 200:
            self.stats.errors += 1
            self.stats.error_urls.append(f"{url} :: HTTP {response.status_code}")
            return None

        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        path = self._write(url, response.content, content_type, response)

        self.stats.fetched += 1
        return CrawlResult(
            url=url,
            local_path=path,
            content_type=content_type,
            status_code=response.status_code,
            fetched_at=datetime.now(UTC).isoformat(),
            from_cache=False,
            depth=depth,
        )

    # --- Cache ------------------------------------------------------------

    def _paths_for(self, url: str) -> tuple[Path, Path]:
        parts = urlparse(url)
        slug = (parts.path or "/").strip("/").replace("/", "__") or "index"
        if parts.query:
            # A STABLE digest, not hash(). Python randomises string hashing per
            # process, so the same URL produced a different cache filename on
            # every run: the cache always missed and the site was re-fetched in
            # full. Politeness depends on this being deterministic.
            digest = hashlib.sha1(parts.query.encode("utf-8")).hexdigest()[:8]
            slug = f"{slug}__q{digest}"
        suffix = ".pdf" if is_pdf_url(url) else ".html"
        base = self.config.output_dir / parts.netloc
        return base / f"{slug}{suffix}", base / f"{slug}.meta.json"

    def _cached(self, url: str) -> CrawlResult | None:
        body_path, meta_path = self._paths_for(url)
        if not (body_path.exists() and meta_path.exists()):
            return None
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return CrawlResult(
            url=url,
            local_path=body_path,
            content_type=meta.get("content_type", ""),
            status_code=meta.get("status_code", 200),
            fetched_at=meta.get("fetched_at", ""),
            from_cache=True,
            depth=meta.get("depth", 0),
        )

    def _write(self, url: str, body: bytes, content_type: str, response: httpx.Response) -> Path:
        body_path, meta_path = self._paths_for(url)
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(body)
        meta_path.write_text(
            json.dumps(
                {
                    "url": url,
                    "final_url": str(response.url),
                    "local_path": str(body_path),
                    "content_type": content_type,
                    "status_code": response.status_code,
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "etag": response.headers.get("etag"),
                    "last_modified": response.headers.get("last-modified"),
                    "content_length": len(body),
                    "user_agent": self.config.user_agent,
                },
                indent=2,
            )
        )
        return body_path

    # --- Link extraction --------------------------------------------------

    def _links_in(self, result: CrawlResult) -> list[str]:
        if "html" not in result.content_type:
            return []
        try:
            html = result.local_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []
        return [urljoin(result.url, href) for href in _LINK_RE.findall(html)]


def _normalise_url(url: str) -> str:
    """Strip fragments and trailing slashes so one page is fetched once."""
    url, _ = urldefrag(url.strip())
    if not url.startswith(("http://", "https://")):
        return ""
    parts = urlparse(url)
    path = parts.path.rstrip("/") or "/"
    rebuilt = f"{parts.scheme}://{parts.netloc}{path}"
    return f"{rebuilt}?{parts.query}" if parts.query else rebuilt
