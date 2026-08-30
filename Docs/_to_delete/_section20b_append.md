
### 20.6 Resolutions (29 Aug 2026)

Both open items from §20.2 and §20.3 were decided and implemented.

**§20.2 — control run added.** `C1_CONTROL` (name `C1-CONTROL`) is C1's chunker
with C0's prompt. It is in `CONFIGURATIONS` and `implemented_configs()`, and
deliberately **not** in `ABLATION_ORDER` — it is a measurement, not a stage of
the proposed system. `CONTROL_ORDER` lists it, and `python -m rag configs`
prints it separately, marked as a control.

The two clean measurements it enables:

| Comparison | Isolates |
| --- | --- |
| C0 → C1-CONTROL | structure-aware chunking (prompt held at C0's) |
| C1-CONTROL → C1 | the grounding prompt (chunking held at C1's) |

To collect it: `--config C1-CONTROL` against the same 20 questions, into
`eval/results/C1-CONTROL`. It reuses C1's index, so no re-indexing is needed —
only the flag differs.

**§20.3 — dead flags removed.** `expand_to_parent` and
`refuse_when_unsupported` are gone from `PipelineConfig` and from `to_dict()`,
so no result file can imply a capability the run did not have. Note that eval
results already written contain the two keys; they are historical records and
were not rewritten. `refuse_when_unsupported` returns in C5, where refusal is
the actual subject.

**A new test that would have caught all of this.**
`test_each_step_changes_exactly_the_fields_recorded_here` compares dataclass
fields between consecutive configurations against an explicit table of expected
deltas. The pre-existing `test_each_step_adds_exactly_one_innovation` compares
`innovations_enabled`, which is a curated label — it certified C1 as
single-variable while C1 was changing two things, and would have gone on doing
so for any number of fields. Adding a field to a preset now fails this test, and
the correct response is to justify a new entry in the table, not to widen it.

Full suite after these changes: **233 passed, 0 failed.**

### 20.7 One more thing Chapter 4 should name: C1 → C2 changes context size

Found while writing the field-level test above, and left unresolved
deliberately — it is the team's call, like §20.2.

C2 sets `dense_top_k=20` (from C1's 5). `Pipeline.ask()` calls
`retriever.retrieve(question, top_k=config.dense_top_k)`, and C2 has no
reranker, so **C2 assembles its answer context from up to 20 chunks where C1
used 5** — bounded only by `max_context_chars=8000`. C3 then reranks that pool
down to `rerank_top_n=5`, returning to C1's context size.

Across the sequence, chunks-in-context goes **5 → 20 → 5**.

This is defensible design rather than an accident: RRF needs a wide pool to fuse
over, and reranking exists precisely to narrow a wide pool well. But it means:

* a C1 → C2 gain is hybrid fusion **and** four times the context;
* part of any C3 → C2 difference is the return to a smaller, cleaner context,
  not only the cross-encoder's judgment.

Three options, in ascending cost:

1. **Name it in Chapter 4.** The C1 → C2 row measures retrieval strategy and
   context width together; say so. Free.
2. **Add a second control**, C2 with `dense_top_k=5`/`sparse_top_k=5`, the same
   shape of fix as C1-CONTROL. One extra run, and it separates fusion from
   width cleanly.
3. **Hold context width constant across the ablation** by giving C1 the wider
   pool too. Cleanest in principle, but it changes C1 and invalidates the C1
   results already collected.

Option 1 is honest and costs nothing; option 2 is what the report would want if
the C1 → C2 gain turns out to be the largest in the table, since that is the
row an examiner will press on.
