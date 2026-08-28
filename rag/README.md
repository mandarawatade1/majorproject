# Knowledge service (`rag/`)

The research contribution lives here. This package knows nothing about FastAPI:
the API imports it, never the reverse. That boundary is what lets the same
pipeline be driven from the web app, the CLI and the evaluation harness — and
what makes the C0-C5 ablation a fair, single-variable comparison rather than a
comparison of two different programs.

| Phase | Module | Status |
|---|---|---|
| 1 | `ingestion/` — crawler, parsers, normaliser, manifest | **complete** |
| 3 | Baseline pipeline **C0**: fixed chunks, dense-only, plain generation | not started |
| 4 | `chunking/`, `enrichment/`, `indexing/`, `retrieval/` — **C1-C3** | not started |
| 5 | `agent/`, `verification/` — **C4-C5** | not started |

## `ingestion/` — Phase 1

```
ingestion/
├── models.py            ParsedDocument, Section, DocumentCategory, SourceType
├── categorise.py        URL -> category and department rules
├── robots.py            robots.txt compliance and crawl-delay
├── crawler.py           polite, cached, single-threaded crawler
├── parsers/
│   ├── sections.py      markdown -> heading tree  (structure-aware foundation)
│   ├── html.py          HTML -> markdown, boilerplate stripped
│   ├── pdf.py           PDF -> text with page numbers on every section
│   └── markdown.py      demo corpus loader; front matter is MANDATORY
├── dedupe.py            suppress identical content, audit the suppression
├── normalise.py         validated write to corpus/normalised/
├── manifest.py          provenance record + real/demo accounting
└── cli.py               python -m rag.ingestion ...
```

### Running it

```bash
docker compose exec api python -m rag.ingestion all       # crawl, parse, manifest, stats
docker compose exec api python -m rag.ingestion crawl     # fetch into corpus/raw/
docker compose exec api python -m rag.ingestion parse     # -> corpus/normalised/
docker compose exec api python -m rag.ingestion manifest  # -> corpus/manifest.json
docker compose exec api python -m rag.ingestion stats     # print statistics
```

The crawl caches every response under `corpus/raw/`. Re-running `parse` and
`manifest` costs the website nothing; only `crawl --refresh` goes back to the
network.

### Crawling policy

Hard-coded, not configurable:

- `robots.txt` is obeyed. `--ignore-robots` exists only to be refused with an
  explanation; there is no flag that disables compliance.
- The User-Agent names the project and carries a contact address.
- Requests are sequential, never concurrent, with at least one second between
  them — or the site's stated `Crawl-delay`, whichever is longer.
- Only the hosts named in `--urls` are ever fetched. A link off-site is dropped.
- Every response is cached with its URL, fetch timestamp, status and ETag.

### What each parser guarantees

**HTML.** trafilatura strips the repeated 13-item navigation, sidebar and
footer before anything is indexed. Without this, site chrome would be the
highest-frequency text in the corpus and would pollute every retrieval. Pages
yielding under 250 characters are dropped as navigation furniture.

**PDF.** Every section carries a page number. Three strategies, in order: the
PDF's own table of contents (authoritative, and present in most institutional
reports), font-size analysis, then one section per page. The last is never
useful but always correct, which guarantees page-level provenance even for a
badly generated file. A PDF yielding almost no text is reported as probably
scanned and needing OCR, rather than silently skipped.

**Demo markdown.** Front matter is mandatory and a file without it is
**rejected**, not defaulted. `title`, `doc_id`, `is_demo`, `demo_reason` and
`category` are all required; `is_demo` must be literally `true`; `demo_reason`
must be a real sentence. See `corpus/demo/README.md`.

### The real/demo guarantee

`is_demo` is set once, at parse time, and is never inferred later. It is
carried on `ParsedDocument`, written into both the `.md` and `.json` outputs,
recorded in `corpus/manifest.json`, and validated by `ParsedDocument.validate()`
before anything reaches disk.

Two invariants are enforced rather than documented:

1. A document in an internal-only category (`sop`, `circular`, `internal_wiki`,
   `lab_manual`, `helpdesk`, `timetable`) **cannot** be marked real. This
   material does not exist publicly, so a real-labelled instance is a bug.
2. A demo document **must** carry a `demo_reason`.

`manifest.py` enforces a **floor on real data**, not a band around a demo
quota: `meets_target` passes when at least 80% of documents are real. The
project brief asks for "~80% real, ~20% clearly labelled demo", and the
guarantee that matters is how much of what the system knows is genuine. A
corpus that is 95% real over-delivers on that; an earlier two-sided check
reported it as a failure, which was a bug in the check.

Demo share is still reported, by document count and by word count, because it
answers a different question: is there enough internal-document coverage to
evaluate that retrieval path? That is settled by counting golden-set questions,
not by a percentage, so it is informational rather than enforced.

### Deduplication

A WordPress site gives many hub pages the same body. On the first real crawl,
68 distinct URLs produced byte-identical extracted text because the only
substantive block on each was a shared "Departments" table — 97 redundant
documents out of 823, about 42,600 wasted words.

That is not merely untidy. Retrieval would return the same table five times for
one question, filling the context budget with a single block. **Context
Precision**, one of the three RAGAS metrics this project reports, measures
exactly that, so duplicates would depress a headline result for a reason
unrelated to the retrieval strategy being evaluated.

`dedupe.py` groups by `content_hash` and keeps one document per group,
preferring real over demo, then the shallowest URL path, then the shortest URL
— the last two are arbitrary but deterministic, so repeated parses do not churn
the manifest.

Suppression is recorded, never silent. Every dropped document keeps its URL in
`corpus/suppressed.json` and in the manifest's `suppressed_duplicates`,
alongside the document that carries its content, so the corpus can still answer
"did you crawl this page?" with a yes.

### Testing

```bash
pytest rag/tests            # from the repo root
```

No network, no database, no model weights. The crawler tests inject a stub
robots policy so nothing reaches out to a real host.
