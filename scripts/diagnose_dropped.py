#!/usr/bin/env python3
"""Report every crawled HTML page that `parse_html` discards, and by how much.

Why this exists
---------------
`cmd_parse` drops a page with a bare `continue` and the comment
"navigation-only page; not an error". That is the only silent exit in the
ingestion pipeline — PDF failures, unreadable metadata and demo errors are all
collected into `failures` and printed, but an HTML page whose extracted text
falls below `MIN_USEFUL_CHARS` leaves no trace in any output, any manifest, or
`suppressed.json`. Twenty-one documents that the earlier corpus contained are
gone this way, including six faculty profiles and the IQAC AQAR reports, and
their raw sources are all still on disk.

So the question this answers is narrow and decisive: are those pages *thin*
(extraction worked, the page really is a stub — the filter is doing its job),
or *broken* (extraction returned almost nothing from a page with real content —
the filter is hiding a parser regression)?

The distinction is visible in the numbers. A stub sits a little under the
threshold and its extracted text reads like a heading and a menu. A parse
failure sits near zero while the raw HTML is tens of kilobytes, and the ratio
of extracted characters to raw bytes collapses. This prints both.

Run it inside the API container, where `rag` is importable:

    docker compose exec api python /app/rag/../scripts/diagnose_dropped.py

or, more simply, from the repository root:

    docker compose exec api python scripts/diagnose_dropped.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CORPUS = Path(os.environ.get("CORPUS_DIR", "/corpus"))


def main() -> int:
    try:
        from rag.ingestion.parsers.html import (
            MIN_USEFUL_CHARS,
            _extract_main_content,
            _extract_title,
            _title_from_url,
        )
    except ImportError as exc:
        print(f"cannot import the HTML parser: {exc}", file=sys.stderr)
        print("run this inside the API container, from the repository root.", file=sys.stderr)
        return 1

    raw = CORPUS / "raw"
    if not raw.exists():
        print(f"no raw corpus at {raw}", file=sys.stderr)
        return 1

    dropped: list[dict[str, object]] = []
    kept = 0
    examined = 0

    for meta_path in sorted(raw.rglob("*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if "pdf" in meta.get("content_type", ""):
            continue

        stem = meta_path.name.removesuffix(".meta.json")
        body = meta_path.with_name(f"{stem}.html")
        recorded = meta.get("local_path")
        if recorded and Path(recorded).exists() and Path(recorded).suffix == ".html":
            body = Path(recorded)
        if not body.exists():
            continue

        examined += 1
        html = body.read_text(encoding="utf-8", errors="ignore")
        url = meta.get("final_url") or meta.get("url", "")

        try:
            markdown = _extract_main_content(html)
        except Exception as exc:  # noqa: BLE001 - a crash is itself the finding
            dropped.append(
                {"stem": stem, "url": url, "chars": -1, "raw": len(html),
                 "title": f"EXTRACTOR RAISED {type(exc).__name__}: {exc}"}
            )
            continue

        chars = len(markdown.strip()) if markdown else 0
        if chars >= MIN_USEFUL_CHARS:
            kept += 1
            continue

        dropped.append(
            {
                "stem": stem,
                "url": url,
                "chars": chars,
                "raw": len(html),
                "title": (_extract_title(html) or _title_from_url(url) or "")[:70],
            }
        )

    print(f"threshold MIN_USEFUL_CHARS = {MIN_USEFUL_CHARS}")
    print(f"examined {examined} crawled HTML page(s): kept {kept}, dropped {len(dropped)}\n")

    if not dropped:
        print("nothing is being dropped by the content-length filter.")
        return 0

    dropped.sort(key=lambda d: -int(d["chars"]))
    print(f"{'extracted':>9} {'raw bytes':>10} {'ratio':>7}  page")
    print("-" * 100)
    for row in dropped:
        chars, rawlen = int(row["chars"]), int(row["raw"])
        ratio = f"{chars / rawlen:.4f}" if rawlen else "-"
        print(f"{chars:>9} {rawlen:>10} {ratio:>7}  {row['stem'][:60]}")
        print(f"{'':>28}  {row['title']}")

    near = [d for d in dropped if MIN_USEFUL_CHARS > int(d["chars"]) >= MIN_USEFUL_CHARS // 2]
    empty = [d for d in dropped if int(d["chars"]) <= 20]
    print(
        f"\n{len(near)} page(s) sit within half the threshold — genuine stubs, the filter"
        f"\n  working as intended."
        f"\n{len(empty)} page(s) extracted 20 characters or fewer. Check the 'raw bytes'"
        f"\n  column for those: a large raw file that extracts to nothing is a parser"
        f"\n  failure wearing the filter's clothes, not a thin page."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
