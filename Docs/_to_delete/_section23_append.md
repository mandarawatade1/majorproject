
---

## 23. C4 validated against the real stack (29 Aug 2026)

§19.8 listed the LangGraph compile-and-invoke path as unverified, because
langgraph cannot be installed in the build environment. It has now run on the
team's machine. This section closes that gap and records what the live runs
showed.

### 23.1 The loop works

`python -m rag ask "…" --config C4 --json`, against the real corpus, Chroma,
BM25 and Ollama:

* the graph compiled and executed `retrieve → decide → retrieve → decide`;
* the decide step produced a well-formed follow-up on the first round —
  `SEARCH: Eligibility criteria for M.E. Computer Engineering at Pillai College
  of Engineering` — parsed correctly by `parse_decision`;
* round 2 returned 20 hits of which **11 were new**, so `add_hits` deduplicated
  9 against round 1 and the reranker received a pool of **31** where C3 would
  have handed it 20;
* reranking ran **once**, over the accumulated pool, in `Pipeline.ask()`;
* `iteration_count`, `iterations`, per-round latencies and `stop_reason` all
  reached the log in the expected shape.

**`stop_reason: repeated_query`.** The model proposed its own previous query
verbatim on round 2, and the guard stopped the loop rather than spending round
3 retrieving identical chunks. This is the small-model failure §19.5 predicted,
observed on the very first live question — which is the argument for having
recorded it as a distinct stop reason rather than letting it average into a
score.

### 23.2 Two defects the live run exposed, both fixed

1. **`dense_hits` and `sparse_hits` came back empty.** `_to_result` set only
   `hits` and `fused_hits`, so a C4 row in `retrieval_logs` was strictly poorer
   than a C3 row in the same table — the log could say what the agent finished
   with but not what each arm contributed, which is one of the questions
   Chapter 4 asks of those rows. `AgentState` now accumulates both as
   deduplicated unions across rounds. Confirmed live: 38 dense, 28 sparse.

2. **The decide prompt did not forbid repetition.** The guard caught the repeat,
   but a round and an LLM call were spent reaching a conclusion an instruction
   can prevent. `DECIDE_SYSTEM` now says so explicitly, and the prompt body
   states that a repeat will be rejected. This is the *decide* prompt only —
   the answer prompt is untouched, so the ablation is unaffected. It did not
   prevent the repeat on the question tested; it is a cheap improvement, not a
   fix, and the guard remains the thing that actually holds.

### 23.3 The measurement problem: this machine's timings vary about tenfold

Recorded prominently because it bears directly on what Chapter 4 may claim.

The **identical command**, run three times within a few minutes, produced:

| Run | `decide_1` | `decide_2` | generation |
| --- | --- | --- | --- |
| 1 | 4,140 ms | 3,196 ms | 19,706 ms |
| 2 | 59,159 ms | 49,714 ms | 26,040 ms |
| 3 | 5,905 ms | 5,435 ms | — |

Run 2 was initially suspected to be caused by the §23.2 prompt change. Run 3,
with that same change in place, came back at 5.9 s — so the prompt is
exonerated and the variance is machine state: an 8 GB machine holding Ollama's
7B model, the cross-encoder, the embedding model, Chroma and PostgreSQL at once
is memory-bound, and a background process changes the result by an order of
magnitude.

**What follows for the report.** A latency column populated by single runs on
this machine measures scheduling luck, not configuration. Either report latency
as a median over repeated runs on an otherwise idle machine, or state the
variance explicitly and refrain from drawing conclusions from small latency
differences between configurations. A C3-vs-C4 latency claim in particular
cannot survive a 10× noise floor, and C4's genuine extra cost — two additional
LLM calls and a wider rerank — is smaller than that noise.

### 23.4 Generation is not deterministic, and the ablation depends on it

Two runs of the same question under C4 retrieved **byte-identical** chunks —
same five reranked ids, same scores — and produced materially different
answers. The first gave only "criteria decided by the State CET Cell"; the
second gave the actual criteria (HSC with Physics and Mathematics, 45% / 40%,
a non-zero MHT-CET score).

`LLM_TEMPERATURE` is `0.1`, not `0`. So identical retrieval does not imply an
identical answer, and **two runs of one configuration differed by more than
some configurations will differ from each other.** Any faithfulness or answer-
relevancy delta drawn from a single run per configuration is confounded with
sampling noise.

Not changed unilaterally, because it is a decision about the whole evaluation
and C0–C3 were collected at 0.1:

1. **Quantify it first.** Run one question three times under one configuration
   and see how far the answers move. Cheap, and it decides the rest.
2. **Set `LLM_TEMPERATURE=0`** and re-collect every configuration. Cleanest,
   costs a full re-run of everything.
3. **Repeat runs per question** (`--repeat N` in the harness) and report a
   median or an agreement rate. Strongest evidence, N× the runtime.
4. **Keep 0.1, single runs, and say so** in Chapter 4 — honest, but it weakens
   every small difference in the results table.

### 23.5 Validated by accident: the demo-data safeguard works end to end

A C3 run on a different question retrieved a synthetic circular
(`DEMO/CE/2026/13`), and the answer carried both the inline `[DEMO DATA]`
marker on the citation and the footer:

```
NOTE: one or more sources are synthetic DEMO DATA and do not describe real
institutional fact.
```

That is the `is_demo` flag propagating parser → manifest → database → chunk →
index metadata → citation → rendered answer, exactly as §2 designed it, and it
is worth a sentence in the report: the 80/20 real-to-demo split is not merely
declared in a manifest, it is visible to a reader at the point of use.

### 23.6 Retrieval quality: a corpus finding, not a C4 finding

On the eligibility question the cross-encoder ranked a **faculty profile page**
first (`Sowmya P. > Education`, score 0.376) above the prospectus page that
actually answers it, and three of the five final sources were faculty pages.
Faculty "Education" sections list *M.E. Computer Engineering* as a degree held,
so both BM25 and the cross-encoder match the phrase strongly.

This affects C2 and C3 identically; C4 may fare marginally worse because a
wider pool offers more faculty pages to choose from. Two related signals from
the same log:

* the sparse arm's top two hits were **demo documents** (BM25 16.88),
  outranking the real prospectus on keyword match;
* eight unrelated documents (library, study tours, galleries, `nba-dcs`) shared
  a cosine score of exactly `0.745055`, which means near-identical boilerplate
  chunks are occupying retrieval slots.

If this is systematic across the 20 questions it belongs in Chapter 5 as a
limitation of the corpus rather than of the architecture. `include_demo_sources
=False` exists precisely so an evaluation run can measure against real data
only, and is worth one comparison run.
