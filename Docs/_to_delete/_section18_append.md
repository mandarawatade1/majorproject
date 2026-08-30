
---

## 18. Phase 4 — C1 to C3 (28 Aug 2026, recorded from handoff)

This phase was carried out in a separate session. It is recorded here so the
document stays a complete history, but with an explicit caveat: **the claims in
this section were reported to me, not verified by me**, except where noted.

### 18.1 What was built

| Config | Adds | Where |
| --- | --- | --- |
| C1 | structure-aware semantic chunking | `rag/chunking/semantic.py` |
| C2 | hybrid dense + BM25, fused with RRF | `rag/retrieval/hybrid.py`, `rag/indexing/bm25.py` |
| C3 | cross-encoder reranking (`bge-reranker-base`) | `rag/reranking/cross_encoder.py` |

All three are wired into `rag/pipeline.py`, indexed, and evaluated against a
20-question set (`eval_questions.json`, `run_baseline_eval.py`, results under
`eval/results/C0` … `C3`).

### 18.2 Three defects found in that session

1. **`rag/ingestion/parsers/html.py`** — the theme's real content wrapper
   (`div.post-content`) was rejected by `MIN_USEFUL_CHARS = 250`, a threshold
   meant for a different fallback path. Fixed with a separate, lower
   `MIN_WRAPPER_CHARS = 40` used only for that high-confidence selector.
2. **`rag/ingestion/cli.py`** — one real URL could arrive behind several raw
   crawl artifacts (a `?p=1234` redirect and a slug URL resolving to the same
   page), producing duplicate `doc_id`s that overwrote each other on disk while
   still being counted as written. Fixed by collapsing same-`doc_id` documents
   before `normalise()`. Corpus reconciled at **765** documents, up from 609.
3. **`run_baseline_eval.py`** — `run_question()` never passed `--config` to the
   `rag ask` subprocess, so every early eval run queried C0 regardless of the
   folder its results were saved under.

The third is the same shape as §14's `file_stem` bug and §11's `.pdf.pdf` bug:
a value correct at one end of a boundary and silently dropped at the other.
It is now three occurrences, which is a pattern rather than bad luck.

### 18.3 What I did verify

Given defect 3, the C1–C3 results were only trustworthy if they postdate the
fix. Checked directly:

* every `eval/results/C{1,2,3}` file is timestamped after the harness fix;
* all 20 answers differ from C0's in each of the three configurations.

Had either check failed, Chapter 4's C0→C3 comparison would have been three
copies of the same run under different labels. The ablation is intact.

---

## 19. Phase 5 — C4, the agentic loop (29 Aug 2026)

### 19.1 The decision that shaped everything else

The obvious way to build C4 is to give the agent the whole question-to-answer
path: a `retrieve` node, a `decide` node and an `answer` node of its own. That
was the direction sketched in the handoff, and it was not taken.

The problem is the `answer` node. The ablation's validity rests on citation and
grounding wording being **identical** across C0 through C5 — otherwise a C4
improvement could be the new prompt rather than the new retrieval. An `answer`
node means a second call site for `assemble_context()` and `build_prompt()`,
and two call sites drift. This project has now been bitten three times (§11,
§14, §18.2) by exactly that: one transformation implemented twice, the copies
diverging silently.

So C4 is shaped as a **`Retriever`**. `AgenticRetriever` satisfies the same
protocol as C0's dense retriever and C2's hybrid one, returns a
`RetrievalResult`, and **`Pipeline.ask()` is not modified at all**. C4 runs the
same reranker call, the same `assemble_context()`, the same `build_prompt()`
and the same generation step as C3 — because it runs the identical code. The
rule is enforced by construction rather than by remembering to keep two prompts
in sync. The only thing C4 changes is how the candidate pool was gathered,
which is what "adds exactly one thing" is supposed to mean.

Reranking therefore happens once, in `ask()`, over the pool accumulated across
every iteration. C4 hands the reranker a richer candidate set than C3 does and
picks the same `rerank_top_n` from it.

### 19.2 One follow-up query per iteration

The open question from the handoff. Chosen: **one**.

Multiple queries per round gather more per LLM call, but they make the ablation
harder to read — with a variable fan-out, "C4 retrieved more" confounds breadth
with depth, and the iteration count stops meaning anything comparable across
questions. One query per round makes `agent_max_iterations` an honest knob and
`iteration_count` an honest number. It also matches what a 4-bit 7B model can
actually produce reliably: one line of output, not a list.

### 19.3 Files

| File | Contains |
| --- | --- |
| `rag/agentic/base.py` | `AgentState`, `AgentIteration`, `StopReason` — no LangGraph import |
| `rag/agentic/decide.py` | the decide prompt and `parse_decision()`, all pure functions |
| `rag/agentic/nodes.py` | `retrieve_node`, `decide_node`, `should_continue` — dependencies passed in |
| `rag/agentic/graph.py` | `AgenticRetriever` and `build_graph()` — wiring only, no logic |
| `rag/tests/test_agentic.py` | 60 tests, none of which import LangGraph |

`RetrievalResult` gains two additive fields, `iterations` and `stop_reason`,
empty and `None` for every single-pass configuration — so a C4 row in
`retrieval_logs` is distinguishable from a C3 row by their presence.

### 19.4 Plain text, not structured output

The decide step asks for exactly one line: `READY`, or `SEARCH: <query>`. Not
JSON, not tool-calling. A quantized 7B model does not reliably emit well-formed
structured output, and the failure mode is what matters: a malformed JSON blob
parsed leniently yields "no follow-up", turning C4 into C3 with nothing
erroring. A one-line contract either matches or visibly does not, and anything
unreadable is **recorded as unparseable** rather than averaged into the results.

### 19.5 Five stop reasons, all recorded

| Reason | Meaning |
| --- | --- |
| `model_says_ready` | the intended path |
| `iteration_cap` | `agent_max_iterations` reached |
| `no_new_chunks` | a round surfaced nothing new; this line of enquiry is exhausted |
| `repeated_query` | the model proposed a query it already ran |
| `unparseable_decision` | the output could not be read; answer with what we have |

The last three mean C4 degraded towards C3 **for that question**. They are
recorded as distinct values precisely so a degradation cannot hide inside an
averaged score — "C4 stopped after two rounds" means something very different
depending on which of these produced it. Expect to report their frequency in
Chapter 4 alongside the accuracy numbers; a C4 that hits `unparseable_decision`
on half the question set has not been measured, it has been mislabelled.

Two of them also save an LLM call: at the cap, and after a barren round, the
answer to "do you need more?" cannot be acted on, and CPU inference is the
budget that matters here.

### 19.6 Two defects found in my own C4 code

Both were found by tests written against the code, not by reading it.

1. **Prose accepted as a search query.** `parse_decision` has a fallback for a
   bare query with no `SEARCH:` prefix, guarded by a blocklist of opening
   phrases. "Hmm, I am not sure what you want me to do here." passed it and
   would have been issued as a retrieval — and, worse, written into
   `rewritten_queries`, where Chapter 4 reads it as a query the agent *chose*.
   A log that misreports the agent's reasoning is worse than one that admits it
   could not read the output. Replaced the blocklist of openings with a token
   filter over the whole line (first/second person, hedges, negation, clause
   punctuation), and lowered the word cap from 15 to 12. The check now errs
   towards rejection, which costs an understated C4 rather than a fabricated
   one.

2. **Retrieval latency reported at roughly double.** `Pipeline.ask()` computes
   retrieval time by summing every value in `stage_latencies`.
   `retrieve_node` was recording both a round total (`retrieve`) *and* the
   inner retriever's breakdown (`dense_search`, `sparse_search`, `fuse`) — the
   parts and the whole, in one dict that gets summed. C4's latency, the exact
   quantity the report must weigh against its accuracy gain, would have been
   inflated ~2×. Now the breakdown is recorded when the inner retriever
   provides one and a round total only when it does not.

### 19.7 Two stale tests repaired

Not C4's doing, but they were failing:

* `test_pipeline.py::TestUnbuiltConfigsAreRefused` still asserted
  `implemented_configs() == ["C0"]` and expected C1/C2 to raise — stale since
  Phase 4 landed. Now asserts the real gate (`C0`–`C4` built, `C5` not).
* `test_manifest.py` imported `TARGET_DEMO_SHARE`, removed in §12 when the gate
  became one-sided. **The whole file failed at collection**, which means the
  repo's test suite has not run clean since then. Its `test_far_off_target_is_reported`
  also still encoded the two-sided band that §12 deliberately removed — it
  asserted a 99%-real corpus *fails*. Replaced with the honest pair: mostly-real
  passes, too-little-real fails.

### 19.8 What was verified, and what was not

| Check | Result |
| --- | --- |
| `rag/tests/test_agentic.py` (60 tests) | pass |
| Full `rag/tests` suite (204 tests) | pass |
| ruff lint and format across `rag/` | clean |
| Parser against `READY`/`SEARCH:`/markdown/lead-ins/prose/empty | pass |
| All five stop reasons, each by its own path | pass |
| Dedup, ordering, per-round latency, log shape | pass |
| C4 differs from C3 in exactly `{name, description, agentic}` | pass |
| **LangGraph `StateGraph` compile and invoke** | **not run** — langgraph is not installable in this build environment (no PyPI) |
| **Against real Chroma / embeddings / Ollama** | **not run**, same reason |

The node bodies and the routing function are tested directly, through a
hand-rolled driver that transcribes the graph's wiring; `build_graph()` itself
contains no branching, and `TestWiring::test_driver_matches_graph_wiring` pins
its shape by inspection so the driver cannot silently drift from it. But the
compile-and-invoke path runs for the first time on the team's machine.

Note that pytest itself is not installable in this environment either; the 204
passing tests were run under a minimal local stand-in providing `parametrize`,
`raises` and `fixture`. **The authoritative run is `docker compose exec api
pytest` on the team's machine**, and that is the first thing to do below.

### 19.9 What the team must run

```bash
docker compose exec api pytest rag/tests -q        # expect 204 passed
docker compose exec api python -c "import langgraph; print(langgraph.__version__)"
docker compose exec api python -m rag ask "What is the eligibility for the M.E. programme?" --config C4
```

The third is the real test: it is the first time the graph compiles. If
langgraph is missing, `build_graph()` raises a message saying exactly that
rather than failing obscurely inside the state machine.

Then compare against C3 on the same question, and check the tail of the answer
for `iteration_count`, `stop_reason` and the per-round latencies.

### 19.10 Gate

`implemented_configs()` now returns `["C0", "C1", "C2", "C3", "C4"]`. C5 still
raises.

C5 (`verify_answer=True`, post-answer verification) is **not designed yet** and
will be scoped with the team before any code is written, as agreed.
