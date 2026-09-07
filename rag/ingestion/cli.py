"""Command-line entry point for corpus ingestion.

    python -m rag.ingestion crawl      fetch pages and PDFs into corpus/raw/
    python -m rag.ingestion parse      parse raw + demo into corpus/normalised/
    python -m rag.ingestion manifest    write corpus/manifest.json
    python -m rag.ingestion stats       print corpus statistics
    python -m rag.ingestion all         crawl -> parse -> manifest -> stats

Run inside the container so the dependencies and paths are the ones the rest
of the system uses:

    docker compose exec api python -m rag.ingestion all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _corpus_dir() -> Path:
    return Path(_env("CORPUS_DIR", "./corpus"))


# ---------------------------------------------------------------------------
# crawl
# ---------------------------------------------------------------------------


def cmd_crawl(args: argparse.Namespace) -> int:
    from rag.ingestion.crawler import CrawlConfig, Crawler

    base_urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    raw_dir = _corpus_dir() / "raw"

    config = CrawlConfig(
        base_urls=base_urls,
        only_seeds=args.only_seeds,
        output_dir=raw_dir,
        user_agent=args.user_agent,
        delay_seconds=args.delay,
        max_pages=args.max_pages,
        respect_robots=not args.ignore_robots,
        refresh=args.refresh,
        max_depth=args.max_depth,
    )

    if args.ignore_robots:
        print(
            "REFUSING: --ignore-robots is not available.\n"
            "This crawler targets a live institutional website. Ignoring robots.txt\n"
            "is not a technical option we expose.",
            file=sys.stderr,
        )
        return 2

    print(f"Crawling {', '.join(base_urls)}")
    print(f"  user agent : {config.user_agent}")
    print(f"  delay      : >= {config.delay_seconds}s between requests")
    print(f"  page cap   : {config.max_pages}")
    print(f"  cache      : {raw_dir}")
    print(f"  refresh    : {config.refresh}\n")

    with Crawler(config) as crawler:
        results = crawler.crawl()
        stats = crawler.stats

    print(f"\n{stats.summary()}")
    if stats.error_urls:
        print(f"\nFirst {min(10, len(stats.error_urls))} errors:")
        for line in stats.error_urls[:10]:
            print(f"  {line}")

    html = sum(1 for r in results if "html" in r.content_type)
    pdf = sum(1 for r in results if "pdf" in r.content_type)
    print(f"\nartefacts on disk: {html} HTML, {pdf} PDF")
    return 0


# ---------------------------------------------------------------------------
# dependency preflight
# ---------------------------------------------------------------------------


def _preflight() -> int:
    """Report missing optional parsers before they can fail silently.

    Without an HTML extractor, every crawled page yields nothing and the run
    ends with "0 real documents" and no explanation. That is a confusing
    failure to debug, so it is caught here instead.
    """

    def _present(module: str) -> bool:
        try:
            __import__(module)
        except ImportError:
            return False
        return True

    trafilatura = _present("trafilatura")
    beautifulsoup = _present("bs4")
    pymupdf = _present("fitz")

    if not trafilatura and not beautifulsoup:
        print(
            "ERROR: no HTML extractor available. Every crawled page would be\n"
            "       dropped without explanation.\n"
            "       Install with: pip install trafilatura beautifulsoup4 lxml",
            file=sys.stderr,
        )
        return 1

    if not trafilatura:
        print(
            "WARNING: trafilatura is not installed; falling back to BeautifulSoup.\n"
            "         Boilerplate stripping will be weaker, so site navigation and\n"
            "         footers may end up in the corpus. Install trafilatura for\n"
            "         the intended behaviour.",
            file=sys.stderr,
        )

    if not pymupdf:
        print(
            "WARNING: PyMuPDF is not installed; PDFs will be skipped and no\n"
            "         page-level provenance will be produced. "
            "Install with: pip install pymupdf",
            file=sys.stderr,
        )

    return 0


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------


def cmd_parse(args: argparse.Namespace) -> int:
    if _preflight() != 0:
        return 1

    from rag.ingestion.dedupe import deduplicate, format_report
    from rag.ingestion.models import ParsedDocument
    from rag.ingestion.normalise import normalise
    from rag.ingestion.parsers.html import MIN_USEFUL_CHARS, parse_html
    from rag.ingestion.parsers.markdown import load_demo_corpus
    from rag.ingestion.parsers.pdf import parse_pdf

    corpus = _corpus_dir()
    raw_dir, demo_dir, out_dir = corpus / "raw", corpus / "demo", corpus / "normalised"

    documents: list[ParsedDocument] = []
    failures: list[str] = []
    thin: list[dict[str, str]] = []

    # --- real: crawled HTML and PDFs ---
    for meta_path in sorted(raw_dir.rglob("*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failures.append(f"{meta_path.name}: unreadable metadata")
            continue

        # Use the post-redirect URL when one was recorded. A WordPress
        # "?p=2075" request can 301 to a real slugged page
        # ("/post-with-youtube-video/") -- the pre-redirect url has no
        # meaningful path, so every such request built the same doc_id
        # ("<host>-home") and silently overwrote every other one on disk.
        # ~245 real pages were lost to this before final_url was consulted.
        url = meta.get("final_url") or meta.get("url", "")
        content_type = meta.get("content_type", "")

        # Derive the body filename by APPENDING the extension to the sidecar's
        # stem, never with Path.with_suffix() — which replaces the last suffix.
        # A PDF URL slug already ends in ".pdf", so the cached file is
        # "<slug>.pdf.pdf"; with_suffix() looked for "<slug>.pdf" and silently
        # skipped every PDF in the corpus.
        stem = meta_path.name.removesuffix(".meta.json")
        html_path = meta_path.with_name(f"{stem}.html")
        pdf_path = meta_path.with_name(f"{stem}.pdf")

        # Crawls from this version onward record the path explicitly, so this
        # class of writer/reader disagreement cannot recur.
        recorded = meta.get("local_path")
        if recorded:
            recorded_path = Path(recorded)
            if recorded_path.exists():
                if "pdf" in content_type:
                    pdf_path = recorded_path
                else:
                    html_path = recorded_path

        try:
            if "pdf" in content_type and pdf_path.exists():
                document = parse_pdf(
                    pdf_path,
                    source_url=url,
                    fetched_at=meta.get("fetched_at"),
                    extract_tables=args.tables,
                )
                if document is None:
                    failures.append(
                        f"{pdf_path.name}: too little extractable text "
                        f"(likely a scanned PDF needing OCR)"
                    )
                    continue
            elif html_path.exists():
                document = parse_html(
                    html_path.read_text(encoding="utf-8", errors="ignore"),
                    url=url,
                    local_path=html_path,
                    fetched_at=meta.get("fetched_at"),
                )
                if document is None:
                    # Below MIN_USEFUL_CHARS of body text. Usually right — a
                    # link hub with no prose — but it is a decision about what
                    # the corpus contains, and until it was recorded here it
                    # was the only one in this pipeline that left no trace: not
                    # in this run's output, not in the manifest, not in
                    # suppressed.json. 168 of 993 crawled pages exit this way,
                    # and nothing downstream could say so.
                    thin.append(
                        {"stem": stem, "url": url, "local_path": str(html_path)}
                    )
                    continue
            elif "pdf" in content_type:
                failures.append(
                    f"{stem}: sidecar says PDF but no body file found at {pdf_path.name}"
                )
                continue
            else:
                continue
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
            failures.append(f"{stem}: {type(exc).__name__}: {exc}")
            continue

        documents.append(document)

    # Same final_url can appear behind more than one raw crawl artifact -- a
    # "?p=1234" query-string request and a slug URL both redirecting to one
    # real page, for instance. Each produces an identical doc_id, and without
    # collapsing them here, normalise() writes each in turn, silently
    # overwriting on disk while still counting every write -- exactly how
    # "written N" can exceed what actually exists in corpus/normalised/.
    seen_ids: dict[str, ParsedDocument] = {}
    duplicate_url_count = 0
    for doc in documents:
        if doc.doc_id in seen_ids:
            duplicate_url_count += 1
            continue
        seen_ids[doc.doc_id] = doc
    if duplicate_url_count:
        print(
            f"same-url duplicates: collapsed {duplicate_url_count} crawl "
            f"artifact(s) resolving to a doc_id already seen"
        )
    documents = list(seen_ids.values())

    real_count = len(documents)

    # --- demo: hand-authored, front matter mandatory ---
    demo_documents, demo_errors = load_demo_corpus(demo_dir)
    documents.extend(demo_documents)
    failures.extend(demo_errors)

    print(
        f"parsed {real_count} real document(s), {len(demo_documents)} demo document(s)"
    )

    # Suppress identical content before anything is written. A hub page whose
    # only substantive block is a shared table is legitimate content once, and
    # noise the other sixty-seven times.
    parsed_total = real_count + len(demo_documents)
    documents, suppressed = deduplicate(documents)
    print(format_report(suppressed, parsed_total))

    _write_discarded_record(corpus, thin)
    if thin:
        print(
            f"discarded {len(thin)} page(s) with under {MIN_USEFUL_CHARS} characters "
            f"of body text (written to corpus/discarded.json)"
        )

    _write_suppression_record(corpus, suppressed)

    result = normalise(documents, out_dir, force=args.force)

    if result.collisions:
        print(
            f"\nABORTED: {len(result.collisions)} document(s) map to a filename "
            f"already used by another.\n"
            f"         Writing would silently destroy one of each pair, so nothing "
            f"was written.",
            file=sys.stderr,
        )
        for stem, first, second in result.collisions[:10]:
            print(
                f"         {stem}\n             {first}\n             {second}",
                file=sys.stderr,
            )
        return 1

    print(
        f"written {len(result.written)}, unchanged {len(result.unchanged)}, "
        f"pruned {len(result.pruned)}"
    )

    # Reconcile what is on disk against what this run decided to keep. The
    # counts drifting apart is exactly how a suppressed duplicate survives into
    # the corpus unnoticed, so say so loudly rather than leaving it to a later
    # reader of the manifest.
    on_disk = len(list(out_dir.glob("*.json")))
    if on_disk != len(documents):
        print(
            f"\nWARNING: {on_disk} documents on disk but {len(documents)} kept by this run.\n"
            f"         corpus/normalised/ does not match the parse. Re-run with --force.",
            file=sys.stderr,
        )
    else:
        print(
            f"reconciled: parsed {parsed_total}, suppressed {len(suppressed)}, "
            f"kept {len(documents)}, on disk {on_disk}"
        )

    if result.rejected:
        print(f"\nREJECTED {len(result.rejected)} document(s) failing validation:")
        for doc_id, problems in result.rejected[:20]:
            print(f"  {doc_id}")
            for problem in problems:
                print(f"      - {problem}")

    if failures:
        print(f"\n{len(failures)} parse failure(s):")
        for line in failures[:20]:
            print(f"  {line}")
        if len(failures) > 20:
            print(f"  ... and {len(failures) - 20} more")

    return 1 if result.rejected else 0


def _write_discarded_record(corpus: Path, thin: list[dict[str, str]]) -> None:
    """Persist pages dropped for having too little body text.

    Written unconditionally, empty list included, so the absence of discards is
    itself recorded rather than indistinguishable from the file never having
    been produced.
    """
    from rag.ingestion.parsers.html import MIN_USEFUL_CHARS

    path = corpus / "discarded.json"
    path.write_text(
        json.dumps(
            {
                "reason": f"under MIN_USEFUL_CHARS ({MIN_USEFUL_CHARS}) of body text",
                "count": len(thin),
                "documents": thin,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_suppression_record(corpus: Path, suppressed: list) -> None:
    """Persist suppressions so `manifest` can report them without re-parsing."""
    path = corpus / "suppressed.json"
    path.write_text(
        json.dumps([s.to_dict() for s in suppressed], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# manifest / stats
# ---------------------------------------------------------------------------


def _read_suppression_record(corpus: Path) -> list[dict]:
    path = corpus / "suppressed.json"
    if not path.exists():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return []


def cmd_manifest(args: argparse.Namespace) -> int:
    from rag.ingestion.manifest import format_stats, load_documents, write_manifest

    corpus = _corpus_dir()
    documents = load_documents(corpus / "normalised")
    if not documents:
        print("No normalised documents found. Run `parse` first.", file=sys.stderr)
        return 1

    suppressed = _read_suppression_record(corpus)
    manifest = write_manifest(documents, corpus / "manifest.json", suppressed)
    print(f"manifest written: {corpus / 'manifest.json'}")
    print()
    print(format_stats(_stats_from(documents, len(suppressed))))

    if not manifest["statistics"]["meets_target"]:
        real_share = manifest["statistics"]["real_share_by_document"]
        print(
            f"\nWARNING: only {real_share:.1%} of the corpus is real data, below the "
            f"80% floor.\n"
            f"         Crawl more real pages, or remove demo documents.",
            file=sys.stderr,
        )
        if args.strict:
            return 1
    return 0


def cmd_stats(_args: argparse.Namespace) -> int:
    from rag.ingestion.manifest import format_stats, load_documents

    corpus = _corpus_dir()
    documents = load_documents(corpus / "normalised")
    if not documents:
        print("No normalised documents found. Run `parse` first.", file=sys.stderr)
        return 1
    print(format_stats(_stats_from(documents, len(_read_suppression_record(corpus)))))
    return 0


def _stats_from(documents: list, suppressed: int = 0) -> object:
    from rag.ingestion.manifest import compute_stats

    return compute_stats(documents, suppressed)


def cmd_all(args: argparse.Namespace) -> int:
    for step in (cmd_crawl, cmd_parse, cmd_manifest):
        code = step(args)
        if code not in (0,):
            return code
        print()
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m rag.ingestion",
        description="Corpus ingestion for the PCE knowledge management system.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_crawl_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--urls",
            default=_env(
                "CRAWL_BASE_URLS", "https://www.pce.ac.in,https://admissions.pce.ac.in"
            ),
            help="Comma-separated base URLs. Only these hosts are ever fetched.",
        )
        p.add_argument(
            "--delay", type=float, default=float(_env("CRAWL_DELAY_SECONDS", "1.0"))
        )
        p.add_argument(
            "--max-pages", type=int, default=int(_env("CRAWL_MAX_PAGES", "1000"))
        )
        p.add_argument("--max-depth", type=int, default=4)
        p.add_argument(
            "--only-seeds",
            action="store_true",
            help="Fetch exactly the --urls given; do not expand the site's sitemap.",
        )
        p.add_argument(
            "--refresh", action="store_true", help="Re-fetch even if cached."
        )
        p.add_argument("--ignore-robots", action="store_true", help=argparse.SUPPRESS)
        p.add_argument(
            "--user-agent",
            default=_env(
                "CRAWL_USER_AGENT",
                "PCE-KMS-AcademicProject/0.1 (B.Tech major project; "
                "contact: bpatil23comp@student.mes.ac.in)",
            ),
        )

    def add_parse_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--force", action="store_true", help="Rewrite unchanged documents."
        )
        p.add_argument(
            "--tables", action="store_true", help="Extract PDF tables (slower)."
        )

    def add_manifest_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero if the 80/20 target is missed.",
        )

    crawl = sub.add_parser("crawl", help="Fetch pages and PDFs into corpus/raw/")
    add_crawl_args(crawl)
    crawl.set_defaults(func=cmd_crawl)

    parse_cmd = sub.add_parser("parse", help="Parse raw + demo into corpus/normalised/")
    add_parse_args(parse_cmd)
    parse_cmd.set_defaults(func=cmd_parse)

    manifest = sub.add_parser("manifest", help="Write corpus/manifest.json")
    add_manifest_args(manifest)
    manifest.set_defaults(func=cmd_manifest)

    stats = sub.add_parser("stats", help="Print corpus statistics")
    stats.set_defaults(func=cmd_stats)

    everything = sub.add_parser("all", help="crawl -> parse -> manifest -> stats")
    add_crawl_args(everything)
    add_parse_args(everything)
    add_manifest_args(everything)
    everything.set_defaults(func=cmd_all)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
