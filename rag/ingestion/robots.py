"""robots.txt compliance.

Uses the standard library's RobotFileParser — no dependency, and it is the
same implementation most well-behaved crawlers rely on. The crawler consults
this before every fetch, and the effective delay is the larger of the site's
stated Crawl-delay and our own configured floor. We are a guest on someone
else's server.
"""

from __future__ import annotations

import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx


@dataclass
class RobotsPolicy:
    """Per-host robots.txt rules, fetched once and cached for the run."""

    user_agent: str
    default_delay: float = 1.0
    timeout: float = 10.0
    _parsers: dict[str, urllib.robotparser.RobotFileParser | None] = field(default_factory=dict)
    _sitemaps: dict[str, list[str]] = field(default_factory=dict)

    def _parser_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        host = _host_root(url)
        if host in self._parsers:
            return self._parsers[host]

        robots_url = urljoin(host, "/robots.txt")
        parser: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
        assert parser is not None
        parser.set_url(robots_url)

        try:
            response = httpx.get(
                robots_url,
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            )
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
                self._sitemaps[host] = _extract_sitemaps(response.text)
            else:
                # No robots.txt is permission to crawl politely, not a failure.
                parser.parse([])
                self._sitemaps[host] = []
        except httpx.HTTPError:
            # Unreachable robots.txt is treated as "disallow nothing, but be
            # extra careful": we still apply our own rate limit and page cap.
            parser.parse([])
            self._sitemaps[host] = []

        self._parsers[host] = parser
        return parser

    def can_fetch(self, url: str) -> bool:
        parser = self._parser_for(url)
        if parser is None:
            return True
        return bool(parser.can_fetch(self.user_agent, url))

    def delay_for(self, url: str) -> float:
        """The larger of the site's Crawl-delay and our configured floor."""
        parser = self._parser_for(url)
        if parser is None:
            return self.default_delay
        try:
            stated = parser.crawl_delay(self.user_agent)
        except Exception:
            stated = None
        return max(self.default_delay, float(stated)) if stated else self.default_delay

    def sitemaps_for(self, url: str) -> list[str]:
        """Sitemap URLs declared in robots.txt, if any."""
        self._parser_for(url)
        return self._sitemaps.get(_host_root(url), [])


def _host_root(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}"


def _extract_sitemaps(robots_text: str) -> list[str]:
    found: list[str] = []
    for line in robots_text.splitlines():
        if line.lower().startswith("sitemap:"):
            value = line.split(":", 1)[1].strip()
            if value:
                found.append(value)
    return found
