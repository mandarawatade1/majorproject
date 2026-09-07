#!/usr/bin/env python3
"""Show what retrieval actually ranked, without waiting for generation.

`ask --json` prints a retrieval log, but only after the model has spent
several minutes writing an answer -- which is a slow way to learn that the
right passage was never retrieved. This runs `prepare()` and stops.

Usage:
    python -m rag.diagnose "question" [--config C3] [--grep TEXT]
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--config", default="C3")
    parser.add_argument(
        "--grep",
        default=None,
        help="Case-insensitive substring; flag hits whose title or path match.",
    )
    args = parser.parse_args()

    from rag.config import get_config
    from rag.factory import build_pipeline

    pipeline = build_pipeline(get_config(args.config))
    prepared = pipeline.prepare(args.question)
    retrieval = prepared.retrieval

    needle = args.grep.lower() if args.grep else None

    def show(label: str, hits: list) -> None:
        print(f"\n=== {label} ({len(hits)}) ===")
        for rank, hit in enumerate(hits, start=1):
            meta = hit.metadata or {}
            title = str(meta.get("document_title", ""))[:58]
            path = str(meta.get("section_path", ""))
            # section_path repeats the title; the tail is the informative part.
            if path.startswith(title):
                path = path[len(title):].lstrip(" >")
            page = meta.get("page_number", -1)
            mark = ""
            if needle and (needle in title.lower() or needle in path.lower()):
                mark = "  <<< MATCH"
            print(
                f"{rank:3d}. {hit.score:8.4f}  {title:58s} | "
                f"{path[:34]:34s} | p{page}{mark}"
            )

    show("retrieved (pre-rerank)", retrieval.hits)
    if retrieval.reranked_hits:
        show("after rerank (what the model sees)", retrieval.reranked_hits)

    if needle:
        pre = sum(
            1
            for h in retrieval.hits
            if needle in str((h.metadata or {}).get("document_title", "")).lower()
            or needle in str((h.metadata or {}).get("section_path", "")).lower()
        )
        post = sum(
            1
            for h in retrieval.reranked_hits
            if needle in str((h.metadata or {}).get("document_title", "")).lower()
            or needle in str((h.metadata or {}).get("section_path", "")).lower()
        )
        print(f"\n'{args.grep}': {pre} in candidate pool, {post} survived rerank")

    print(f"\nstages: {retrieval.stage_latencies}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
