
---

## 21. C0–C3 correctness audit (29 Aug 2026)

§20 read C0–C3 for *design*. This is the pass that read them for *defects*:
`dense.py`, `chroma.py`, `memory.py`, `bm25.py`, `hybrid.py`,
`cross_encoder.py`, `fixed.py`, `semantic.py`, `chunking/base.py`,
`prompts.py`, `factory.py`, `__main__.py` and `run_baseline_eval.py`.

Three defects, all of the same family: **nothing raises, the run completes, and
the numbers were computed over the wrong thing.**

### 21.1 `--reset` never reset the sparse index

`cmd_index` called `pipeline.index.reset()` and nothing else. The BM25 pickle
survived every rebuild.

Why that is worse than it sounds. `Chunk.chunk_id` defaults to a fresh
`uuid.uuid4()`, so re-chunking the same corpus produces **different ids for
identical text**. RRF fuses dense and sparse hits **by `chunk_id`**. So after
`index --config C2 --reset`:

* Chroma holds the new run's chunks under new ids;
* BM25 holds the new run's chunks *and* every earlier run's, under ids that
  exist nowhere in Chroma;
* those stale entries can outrank the live ones on BM25 score and enter the
  fused list as singletons that no dense hit can ever pair with.

The "ranked highly by both arms" boost — the entire reason RRF was chosen over
score averaging — degrades quietly toward a concatenation of two lists. C2's
headline mechanism weakens with every re-index, and no output says so.

**Fixed.** `--reset` now resets the sparse index too, with the reasoning in a
comment so it is not "tidied up" later.

### 21.2 One Chroma collection, two different chunkers

`CHROMA_COLLECTION` defaults to `pce_chunks` for every configuration. C0 chunks
every 512 characters; C1 onward chunks on section boundaries. Index C1 on top of
a C0 collection without `--reset` and the collection holds a **mixture**, with
every configuration thereafter retrieving over some other configuration's
chunks.

Compounding it: because chunk ids are random, Chroma's `upsert` can never
update. Re-indexing the *same* config without `--reset` does not refresh the
collection, it **doubles** it.

The codebase already had exactly the right instinct here — `ChromaIndex`
refuses a collection built with a different *embedding model*, on the grounds
that a mismatch "returns confident, meaningless results" rather than failing.
That argument applies verbatim to the chunker; it just had not been made.

**Fixed.** The collection now records `chunking` alongside `embedding_model`,
and a mismatch raises with the remedy in the message (`--reset`, or a different
`CHROMA_COLLECTION`). Both checks share one `_check` helper. **Limitation,
stated plainly:** a collection built before this key existed has no `chunking`
recorded and cannot be checked — the first rebuild is what starts the
protection.

### 21.3 The eval harness could not parse a hyphenated config name

`TIMING_RE` matched the config label as `\w+`, which excludes `-`. Given
`[C1-CONTROL | … | retrieval 7025ms, generation 65571ms]` the pattern fails
outright, and `parse_timings` returns empty strings rather than raising — so
**every latency cell for C1-CONTROL would have been silently blank.**

This one is mine: the harness was correct until §20.6 introduced a config name
with a hyphen in it. Fixed to `[\w-]+` and verified against both
`C1-CONTROL` and `C4`. The `--config` help text and the module's "Assumptions"
block were also stale — both still described `--config` as a label that is not
passed through, which is the bug §18.2 fixed. Updated, with the re-indexing
requirement spelled out.

### 21.4 What the team must do about the indexes

The two fixed defects mean **existing indexes may already be contaminated**,
and nothing in the results would show it. Before collecting any more numbers:

```bash
docker compose exec api python -m rag index --config C0 --reset   # fixed chunks
# run C0 eval, then:
docker compose exec api python -m rag index --config C1 --reset   # structure-aware
# run C1, C1-CONTROL evals (same chunker, same index — no re-index between them)
docker compose exec api python -m rag index --config C2 --reset   # + BM25
# run C2, C3, C4 evals (same chunker and index; C3/C4 differ only after retrieval)
```

The grouping matters and is worth stating once: **the index depends only on the
chunker.** C1 and C1-CONTROL share one index; C2, C3 and C4 share another,
because reranking and the agent act after retrieval and change nothing about
what was indexed. Only C0 ↔ C1 crosses a chunker boundary, and that is now the
one transition that raises if you forget `--reset`.

If any C0–C3 results were collected without a `--reset` between chunker
changes, they are suspect and should be re-collected.

### 21.5 A recommendation not taken unilaterally: deterministic chunk ids

The root cause under both §21.1 and §21.2 is that `chunk_id` is random per run.
Deriving it instead as a UUID5 over `(document_id, chunk_index, content_hash)`
would make `upsert` genuinely idempotent, make dense and sparse ids agree by
construction rather than by being built in one process, and make a re-index
safe by default instead of safe-if-you-remember-a-flag.

Not done here, because chunk ids are also the primary keys of the `chunks`
table in PostgreSQL: changing how they are generated means re-seeding, and that
is a data-layer decision rather than a retrieval one. Recommended for after the
current evaluation round, not during it.

### 21.6 What was checked and found sound

Recorded so this audit is not re-run from scratch:

* `assemble_context` — `[Sn]` markers assigned by rank, budget enforced from
  the tail, `dropped_for_budget` counted; a single oversized first chunk is
  admitted rather than yielding empty context. Correct.
* `ChromaIndex.search` — converts cosine **distance** to similarity (`1 - d`).
  This is right, and getting it wrong would have inverted every score in the
  logs while leaving the ranking correct — a discrepancy nobody finds until
  Chapter 4.
* `reciprocal_rank_fusion` — `1/(k + rank)`, `k` taken from `rrf_k` rather than
  hardcoded, first-seen hit retained per id, deterministic ordering. Correct.
* `BM25Index.search` — filters after scoring, drops zero-score hits so an
  unrelated chunk cannot enter the fusion on a rank alone. Correct.
* `CrossEncoderReranker.rerank` — `strict=True` on the score/hit zip, empty
  input handled, returns new `IndexedHit`s carrying the cross-encoder score.
  Correct.
* `DenseRetriever` — leaves `sparse_hits`/`fused_hits` empty, which is what
  makes a C0 row distinguishable from a C2 row in `retrieval_logs`. Correct.
* `Chunk.citation_label` — strips the duplicated title prefix from
  `section_path`, appends page number when present, marks `[DEMO DATA]`.
  Correct, and duplicated deliberately on `IndexedHit`.
* `StructureAwareChunker` — never splits across a section; a section's
  `start_page` is stamped on all its chunks rather than interpolated, which is
  a documented simplification rather than fabricated precision.

Suite after this phase: **244 passed, 0 failed** (11 new in
`rag/tests/test_index_hygiene.py`).

Two files fail `ruff format --check` on the team's machine —
`rag/chunking/semantic.py` and `rag/tests/test_dedupe.py`. Both predate this
work and were left untouched, but they will trip a CI format gate.
