
---

## 20. Audit of C0–C3 (29 Aug 2026)

C4 wraps C3, so before trusting C4 I went back and read C1, C2 and C3 as
implemented rather than as described in the handoff. Four things came out of
that. The first two matter for Chapter 4; the last two are mine to own.

### 20.1 The reranker is not the model this document names

`rag/reranking/cross_encoder.py` uses **`cross-encoder/ms-marco-MiniLM-L-6-v2`**.
This document names `BAAI/bge-reranker-base` in four places (§2, §3, the
pipeline diagram, and my own §18 table, all now annotated).

The substitution looks deliberate and well-reasoned — the module's docstring
justifies it as ~80 MB and CPU-friendly, matching the 8 GB RAM constraint from
Report Table 3.1, the same reasoning that chose BM25 over a heavier sparse
method. Nothing is wrong with the code. What was wrong is that the change never
reached the documents.

**Action for the team:** if the report's §3.2.1 names `bge-reranker-base`, it
now describes a model the system does not load. Either update the report to the
MiniLM cross-encoder (with the hardware justification, which is a *better* story
than the original) or change the code back. Do not leave them disagreeing — an
examiner who runs the code will find the mismatch.

### 20.2 The C0 → C1 step changes two things, not one

This is the important one.

`C1_STRUCTURE_AWARE` overrides four fields relative to C0:

```python
chunking=ChunkingStrategy.STRUCTURE_AWARE,
enforce_citations=True,
refuse_when_unsupported=True,
expand_to_parent=True,
```

`enforce_citations` is not a labelling flag. In `rag/generation/prompts.py` it
selects `GROUNDED_SYSTEM` over `BASE_SYSTEM` *and* changes the instruction
appended to the user prompt. So C0 and C1 are answered by **different prompts**.

A measured C0 → C1 improvement is therefore the combined effect of
structure-aware chunking **and** a grounding/citation prompt. It cannot be
attributed to chunking, which is what a row labelled "structure-aware chunking"
in Chapter 4 would claim.

Two further points make this worth acting on rather than noting:

* `innovations_enabled` counts only `chunking`, so C1 reports exactly one
  innovation. `TestTheAblationIsSingleVariable` passes. **The test certifies the
  label, not the behaviour** — it compares the curated innovation list, not the
  configuration fields. It would pass no matter how many other fields C1 flipped.
* The confound is confined to this one step. C1 → C2 → C3 → C4 all share
  `enforce_citations=True`, and I verified C4 differs from C3 in exactly
  `{name, description, agentic}`. Every comparison from C1 onward is genuinely
  single-variable; only the first step is affected.

**Three ways forward, for the team to choose:**

1. **Add a control run.** Evaluate a C1 variant with `enforce_citations=False`
   (structure-aware chunking, C0's prompt). The C0 → C1-control delta is then
   chunking alone, and C1-control → C1 is the prompt alone. Costs one extra
   20-question run and turns a confound into two clean measurements — the
   strongest option for the report.
2. **Move the prompt change to its own step**, renumbering the ablation. Most
   faithful to the "one variable per step" claim, most disruptive: every result
   already collected under C1–C3 would need relabelling.
3. **Report it honestly as a two-factor step.** Cheapest, costs nothing already
   measured, but Chapter 4 must then say that the C0 → C1 row measures chunking
   and grounding together and must not claim otherwise.

I have deliberately not chosen. It changes what the report can claim, so it is
not mine to decide.

### 20.3 Two dead configuration flags

`expand_to_parent` and `refuse_when_unsupported` are set on C1 and inherited by
C2–C5, and both appear in `PipelineConfig.to_dict()` — which is what gets
serialised into results. **Neither is read anywhere in `rag/`.** Parent-document
expansion and explicit refusal are not implemented.

They are not counted in `innovations_enabled`, so they inflate no headline
number. But they will appear in any dumped configuration as though they were
active. Either implement them, or drop them from the dataclass so a result file
cannot imply a capability the run did not have. My recommendation is to drop
them now and reintroduce `refuse_when_unsupported` in C5, where refusal is
actually the subject.

### 20.4 My "full test suite" claim in §19.8 was two files short

I reported 204 passing tests across `rag/tests`. The working copy I had staged
was missing `test_dedupe.py` and `test_normalise.py`; the repository has ten
test files, not eight. Re-synced from the repository and re-ran: **229 passed,
0 failed**, with `rag/chunking/semantic.py` also refreshed (my copy of C1's
chunker was stale, which is exactly why this mattered — I had been reasoning
about C4's inputs from an out-of-date C1).

The correction is the point. "The full suite passes" is worth nothing if the
speaker has not checked what "full" is, and the check was one command.

### 20.5 What I now know about C0–C3, having read them

Recorded so the next session does not have to re-derive it:

* **C0** — `FixedSizeChunker` (512/64), dense-only via `DenseRetriever`, top-5,
  `BASE_SYSTEM`, no citations. Chunks carry no `section_path` and no
  `page_number`, honestly, because a fixed window has no section to belong to.
* **C1** — `StructureAwareChunker` (max 1024, overlap 128) chunks *within*
  `document.substantive_sections`, never across a heading, falling back to one
  whole-document section when a document has none. Every chunk carries
  `section_path`; a section's `start_page` is stamped on all its chunks rather
  than interpolated — a documented simplification, not a defect. Plus the
  prompt change of §20.2.
* **C2** — `HybridRetriever` runs dense (top-20) and BM25 (top-20) in parallel
  and fuses by Reciprocal Rank Fusion, `1/(k+rank)` with `k=60` taken from
  `rrf_k` rather than hardcoded. RRF rather than score averaging because cosine
  similarity and BM25 scores are on incomparable scales. BM25 is a pickled
  `rank_bm25` index on disk, filtered after scoring, dropping zero-score hits.
* **C3** — `CrossEncoderReranker` rescores the fused pool jointly on
  (query, chunk) and returns `rerank_top_n=5`. Called from `Pipeline.ask()`,
  not from the retriever.

**The consequence for C4**, which is why this mattered: `ask()` calls
`retriever.retrieve(question, top_k=config.dense_top_k)` — 20 for C3 and C4
alike — so the agent runs the *hybrid* retriever up to three times and hands
the reranker up to ~60 candidates where C3 hands it 20. That is the intended
mechanism. It also means **C4's reranking step costs up to 3× C3's**, since a
cross-encoder scores every pair. Expect that in the latency column; it is real
work, not overhead, and it is recorded under `rerank` in `stage_latencies`.
