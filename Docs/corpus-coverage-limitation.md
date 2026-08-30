# Corpus coverage: what the ingestion pipeline excludes, and why

*Draft for the limitations section. Every figure below was measured on the
corpus the evaluation ran against; none is estimated.*

## The measurement

The HTML parser discards any page whose extracted body text falls below
`MIN_USEFUL_CHARS = 250`. Running the extractor over the full crawl:

| | count |
|---|---|
| Crawled HTML pages examined | 993 |
| Retained | 825 |
| **Discarded below the threshold** | **168** |
| PDFs crawled | 170 |
| Duplicate documents suppressed | 20 |
| Documents in the final manifest | 765 (726 real, 39 demo) |

## What the discarded pages are

Three were inspected by hand rather than assumed.

**`accreditation/nirf`** — 217 KB of raw HTML, of which the body is 244
characters: four link labels and no prose. The bulk of the file is the site's
mega-menu, which the extractor correctly strips. The threshold is right here;
there is no text to lose.

**`extension/uber-rang`** — 246 characters: one descriptive sentence and a list
of years linking to past editions. Again a link hub.

**`academics/bachelors/automobile-engineering/curriculum`** — the exception,
and the one that matters. The extractor returned 247 characters, but the page's
`post-content` wrapper holds roughly 1,246 characters and **16 links to
syllabus PDFs**. The extraction library treats a block consisting mostly of
anchors as navigation boilerplate. On this site that heuristic is inverted:
pages whose entire purpose is to list official documents are exactly the pages
whose content is links.

## The downstream consequence

The exclusion does not stop at the hub page. None of those 16 syllabus PDFs
appear in `corpus/raw`, and no AQAR report PDF was crawled at all, though 170
PDFs were crawled overall. A question such as *"what subjects are in the B.Tech
Automobile Engineering syllabus?"* is therefore unanswerable from this corpus —
not because a PDF failed to parse, but because the page listing those PDFs never
became a document, and the crawl did not reach what it pointed at.

The same pattern accounts for the 23 documents present in an earlier corpus and
absent from the current one: six faculty directory profiles, four student
association pages, the IQAC AQAR reports index, the mandatory disclosure
annexure, and others. Two of the 23 are not losses — `academics/admissions` and
`academics/ph-d` were landing pages now superseded by more specific children.

## Why the exclusion was invisible

Every other rejection in the ingestion pipeline is recorded. PDF extraction
failures, unreadable crawl metadata and malformed demo documents are collected
and printed; suppressed duplicates are written to `corpus/suppressed.json`. The
length-threshold rejection was a bare `continue` with the comment
*"navigation-only page; not an error"*. It appeared in no output, no manifest,
and no record file. A run could report "parsed 785 documents" while discarding
168 pages without a word.

This was found only because an administrative endpoint compared database
document counts against the manifest and the two disagreed — two development
phases after the discards happened.

The pipeline now writes `corpus/discarded.json` on every parse and prints the
count, so the figure in the table above is reproducible rather than
archaeological.

## Assessment

For 167 of the 168 pages the threshold is defensible: they carry no prose, and
admitting them would put navigation fragments into the retrieval index, which is
what the threshold exists to prevent. The link-list case is a genuine defect,
and the honest description of its impact is a **coverage gap in curriculum and
accreditation documents**, not a retrieval or generation failure. Nothing the
system retrieves is wrong; some things it cannot retrieve at all.

The gap was not closed before evaluation because closing it requires re-crawling
to follow the linked PDFs, re-parsing, rebuilding both the dense and sparse
indexes, and re-running all seven configurations over 140 questions. The
evaluation evidence was judged more valuable than the additional coverage.

## Future work

1. Treat a `post-content` block that is predominantly links as content rather
   than boilerplate, extracting anchor text and `href` together, so a page that
   lists documents is indexed as a list of documents.
2. Enqueue PDF links found inside retained pages, so a hub page's targets are
   crawled even when the hub itself is discarded.
3. Lower `MIN_USEFUL_CHARS` only after (1), since the current threshold is doing
   useful work against navigation fragments and lowering it first would admit
   them.
