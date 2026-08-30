
---

## 25. Phase 6 — C5, post-answer verification (29 Aug 2026)

The last configuration. Scoped with the team before any code was written, as
agreed in the handoff.

### 25.1 What C5 adds, and what it must not touch

After the answer is generated, split it into sentences, show them numbered
alongside the context they were written from, and ask the model which of them
state a fact the context does not support.

The constraint is the same one that shaped C4: **generation is untouched.**
Retrieval, reranking, context assembly and the answer prompt are byte-for-byte
C4's, and verification happens afterwards. So a C4-to-C5 difference is the
check and nothing else. Confirmed by the field-level test — C5 differs from C4
in exactly `{name, description, verify_answer}`.

### 25.2 Three decisions the team made

| Decision | Chosen | Why |
| --- | --- | --- |
| On failure | **Annotate; refuse only if *no* sentence is supported** | Flagging is non-destructive and yields a support rate. Total refusal addresses the out-of-scope weakness §24.4 exposed, where C4 was at its worst. |
| Granularity | **One call per answer** | Per-sentence is ~4× the calls; on this hardware that turns a 90-minute evaluation into three hours. |
| Verifier model | **The generator's own model** (`qwen2.5:7b`) | No model swap on an 8 GB machine. And `llama3.1:8b` is the *evaluation judge* — wiring it inside the system would put the examiner into the thing examined, and no Chapter 4 number computed that way would mean what it appears to. |

### 25.3 Why this might work where C4 did not

Worth stating as a prediction the results will test, not as optimism.

C4 asked the model to **plan**: decompose a question, identify a missing fact,
compose a query targeting it. It rephrased the question 12 times out of 12
(§24.3). C5 asks a different kind of question — *does this sentence follow from
this passage?* — which is entailment checking rather than generation, and small
quantized models are markedly better at it.

There is also direct evidence for the format: C4's identical one-line contract
produced **zero unparseable outputs across 20 questions** on the same model. The
verifier reuses that shape rather than inventing a second one.

If C5 also fails, that is a stronger finding than C4's, because the two failures
together would say something specific about what a 4-bit 7B model can and
cannot be asked to do inside a RAG pipeline.

### 25.4 Files

| File | Contains |
| --- | --- |
| `rag/verification/base.py` | `Verdict`, `VerificationResult`, the `Verifier` protocol — no model dependency |
| `rag/verification/claim_check.py` | the prompt, the sentence splitter, `parse_verdict`, `ClaimVerifier` |
| `rag/tests/test_verification.py` | 48 tests, no Ollama |

`Answer` gains a `verification` field, `None` for every earlier configuration —
the same convention `RetrievalResult.stop_reason` follows for C4, so a C5 row
is distinguishable from a C4 row by its presence.

### 25.5 Four rules that make a refusal safe

C5 is the only configuration that can replace a generated answer, so the
conditions under which it does are narrow and each is tested.

1. **A refusal fires only when every checked sentence is unsupported.** Partial
   failure annotates; it never suppresses.
2. **An unreadable verdict never refuses.** It is recorded as `UNPARSEABLE`,
   `checked` stays 0, and the answer is shown unchanged. C4 set this precedent:
   a parse failure must not silently change an outcome. Without it, a broken
   verifier would delete good answers and report the generator as
   hallucinating.
3. **Verdict numbers that index no sentence are dropped, not escalated.**
   `UNSUPPORTED: 7, 8` on a two-sentence answer yields an empty list, not a
   refusal — otherwise the answer would be destroyed on the strength of two
   numbers pointing at nothing.
4. **Empty context is skipped without an LLM call.** The "no information"
   answer has nothing to verify against; checking it would spend a CPU-minute
   concluding that an answer about missing context is unsupported by the
   missing context, and then refuse it.

`SKIPPED` and `UNPARSEABLE` are distinct verdicts from `UNSUPPORTED`, and
`support_rate` is `None` rather than `1.0` when nothing was checked. An
unexamined answer is not a perfect score, and a mean that silently read those
as 1.0 would report the system as fully grounded precisely when it was never
examined.

**A refusal is auditable.** `original_answer` is kept and printed with the
refusal, so a reader can see what was withheld. Suppressing text invisibly
would make C5 unfalsifiable — nobody could tell a caught hallucination from a
destroyed good answer, which is the first question a refusal invites.

### 25.6 The sentence splitter, and a trade-off taken deliberately

Naive splitting on `". "` breaks this corpus badly. It is largely faculty
pages: "Dr. Sowmya P.", "Suhas J. Lawand", "K. Charumathi", "Y. I. Jinesh
Melvin", plus "B.E.", "M.Tech." and "Ph.D." throughout. A mis-split leaves a
subjectless fragment, a fragment is trivially unsupported, and **bad splitting
would raise the measured hallucination rate without anything erroring** — the
project's characteristic failure mode.

So a single letter before a full stop is treated as an initial. The cost is
accepted knowingly and in one direction: a real sentence ending in one letter
("…accredited by NAAC with grade A.") is merged with the next, giving the
verifier one longer sentence to judge. That is a mild loss; the opposite error
manufactures a false hallucination. Both behaviours are pinned by tests,
including the limitation.

### 25.7 What was verified, and what was not

| Check | Result |
| --- | --- |
| `rag/tests/test_verification.py` (48 tests) | pass |
| Full suite | **295 passed, 0 failed** |
| ruff lint and format | clean |
| C5 differs from C4 in exactly `{name, description, verify_answer}` | pass |
| Splitter against real corpus name and degree forms | pass |
| All four refusal rules | pass |
| **Against real Ollama** | **not run** — no Ollama in this build environment |

`implemented_configs()` now returns every configuration. The gate stays: each
phase had to move it deliberately, and that is what stopped a half-built stage
being measured under a finished name.

### 25.8 What the team must run

```bash
docker compose exec api pytest rag/tests -q        # expect 295 passed

docker compose exec api python -m rag ask "What is the intake for Computer Engineering?" --config C5 --json
```

The index C5 needs is the one C4 used — same chunker, same retrieval; C5
changes only what happens after generation. **No re-indexing.**

In the JSON, read `verification`: `verdict`, `support_rate`, `unsupported`, and
`refused`. Then the full run:

```bash
python3 run_baseline_eval.py --config C5 --compare C4
```

`--compare C4` answers the question that matters, exactly as it did for C4:
how often did the extra pass change what the reader sees. Expect roughly 90
minutes plus one verification call per question.
