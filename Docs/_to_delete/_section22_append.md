
---

## 22. The C0 results are not C0 (29 Aug 2026)

You are right that the two §20.6 fixes are additive and invalidate nothing:
dropping `expand_to_parent` and `refuse_when_unsupported` changed no behaviour
because no code read them, and C1-CONTROL is a new configuration that touches
no existing run. Neither is a reason to re-collect anything.

The §21.2 concern was a different one — how the *index* was built before those
runs — and rather than argue it, it is checkable against the saved results.
It was checked. **The C0 evaluation was run against a structure-aware index.**

### 22.1 The evidence

Two independent signals, both from `eval/results/` as committed.

**1. C0 and C1 retrieved byte-identical sources on 20 of 20 questions.**

| Comparison | Questions with identical cited sources |
| --- | --- |
| C0 vs C1 | **20 / 20** |
| C1 vs C2 | 0 / 20 |
| C2 vs C3 | 0 / 20 |
| C0 vs C3 | 0 / 20 |

The three zeros are the control on the method: the comparison discriminates
sharply everywhere else, so 20/20 is not an artifact of how the citations are
parsed. If C0 had queried a fixed-chunk index and C1 a structure-aware one, the
retrieved text would differ on essentially every question — different
boundaries, different embeddings, different neighbours. Identical on every
question means both queried the same index.

**2. 60 of C0's 88 citations carry a section path.**

`FixedSizeChunker` sets `section_path=None` and `page_number=None` on every
chunk it produces. This is deliberate and asserted by the project's own test,
`test_c0_chunks_carry_no_section_or_page` — a fixed window spans arbitrary
parts of a document, so there is no section it honestly belongs to. A C0
citation should therefore read `Pce Prospectus 2022.Pdf` and nothing more.

The saved C0 output reads:

```
  [S1] Wp Content  Uploads  2022  12  Pce Prospectus 2022.Pdf > Page 36 > page 39
```

A section path and a page number, neither of which C0's chunker can emit.

### 22.2 What this means for Chapter 4

C0 ran the C0 *pipeline* — fixed-chunking config, dense top-5, `BASE_SYSTEM`,
no citation instruction — over C1's *chunks*. The chunker is selected at index
time; `rag ask` never re-chunks anything.

So across C0 → C1 the chunking was **identical in both runs**, and the only
thing that differed was `enforce_citations`. Which gives:

* **The C0 → C1 row measures the grounding prompt alone.** It contains no
  signal about structure-aware chunking whatsoever.
* Any Chapter 4 claim attributing a C0 → C1 gain to semantic chunking is
  unsupported by the data collected.
* This compounds §20.2 rather than duplicating it. §20.2 said the step changed
  two variables; the measurement turns out to have changed only one, and it was
  the other one.
* **C1, C2 and C3 remain valid.** They share the structure-aware chunk base
  they were supposed to have, and they differ from one another exactly as their
  configurations predict. Nothing about C1 → C2 → C3 → C4 is affected.

### 22.3 The remedy is one run, not four

The useful consequence. At query time, "the C0 pipeline over a structure-aware
index" is **precisely the definition of C1-CONTROL**: C1's chunking with C0's
prompt, dense top-5, no citations. C1-CONTROL differs from C1 only in
`enforce_citations`, and chunking cannot differ at query time.

So the existing `eval/results/C0` is a valid C1-CONTROL dataset that has been
filed under the wrong name. The control run proposed in §20.6 has, in effect,
already been collected — and what is actually missing is a genuine C0.

```bash
docker compose exec api python -m rag index --config C0 --reset   # FIXED chunks
docker compose exec api python -m rag index  # verify: count differs from C1's
python run_baseline_eval.py --config C0
```

The `--reset` now raises if the collection was built with a different chunker
(§21.2), so this is the one transition that can no longer be got wrong
silently.

**On the existing C0 directory:** re-running it under `--config C1-CONTROL`
against the structure-aware index is cleaner than renaming the folder, and
costs one 20-question pass. The saved summary lines say `[C0 | …]`, so a rename
alone would leave files whose contents contradict their label — the exact
species of problem this section exists to catch. If it is renamed rather than
re-run, that decision must be stated in Chapter 4, not left for a reader to
discover.

### 22.4 What could not be determined

The §21.1 sparse-index question — whether BM25 accumulated stale entries across
re-indexes — **cannot be answered from the saved artifacts**, and no claim is
made either way.

Repeated citation *labels* within one answer (C0: 8, C1: 8, C2: 7, C3: 22) look
like a candidate signal but are not one: a label is
`title > section > page`, which several distinct chunks from the same section
legitimately share. C3's higher count is consistent with the reranker
concentrating its top-5 in the best-matching section, which is desirable
behaviour, not duplication.

Deciding it needs chunk ids, which `run_baseline_eval.py` does not save — it
captures stdout, and the ids are only printed under `rag ask --json`. Worth
adding `--json` to the harness before the next collection round, so the next
audit of this kind is arithmetic rather than inference.
