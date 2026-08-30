
---

## 24. C4 evaluation results — the agent iterates but rarely changes anything (29 Aug 2026)

20 questions, 69.4 minutes, structure-aware index shared with C2 and C3.
`eval/results/C4/`.

### 24.1 What the agent did

| Stop reason | Count |
| --- | --- |
| `model_says_ready` | 8 / 20 |
| `iteration_cap` | 7 / 20 |
| `repeated_query` | 5 / 20 |
| `no_new_chunks` | 0 |
| `unparseable_decision` | 0 |

Mean iterations 1.95. **Zero unparseable decisions across 20 questions** — the
plain-text one-line contract (§19.4) held perfectly against a 4-bit 7B model,
which was the design's biggest risk and is worth stating as a result in its own
right.

### 24.2 The number that matters: 2 / 20

Comparing the five sources actually handed to the generator, C4 against C3 on
the same questions:

| | |
| --- | --- |
| Final sources **identical** to C3 | **18 / 20** |
| Final sources **changed** by the agent | **2 / 20** |

C4 costs roughly three times C3's retrieval and adds up to two extra LLM calls
per question, and on 18 of 20 questions the reranker selected exactly the
chunks C3 selected. The widened pool contained nothing it preferred.

The two that changed are not improvements:

* **q02** — C3 named the M.Tech *and* Ph.D. programmes; C4 dropped the Ph.D.
  line. Less complete.
* **q09** — asked about **Computer Engineering** placements. C3 answered about
  Computer Engineering (from an IT-department source); C4's answer opens "The
  placement record for the **Information Technology** department". Both are
  citing the wrong department's page; C4 is more explicit about doing so.

So on the evidence collected: **C4 changed the outcome on 10% of questions, and
neither change was for the better.**

### 24.3 Why: the follow-up queries are rephrasings, not gap-targeting

Every one of the 12 follow-ups restates the original question. Examples,
against the originals:

| Question | Follow-up the agent chose |
| --- | --- |
| What is the intake for Computer Engineering…? | `What is the intake for Computer Engineering at Pillai College…` |
| What postgraduate programmes does the CE dept…? | `Postgraduate programmes offered by Pillai College of Engineering` |
| What entrance exams are accepted…? | `entrance exams accepted by Pillai College of Engineering` |
| What is the weather forecast for Mumbai this week? | `weather forecast mumbai this week` |

`DECIDE_SYSTEM` instructs, in as many words, to "make the query target that
missing fact — not a rephrasing of the original question". The model ignored
that instruction on **12 of 12** follow-ups.

This explains 24.2 completely. A rephrased query embeds close to the original,
retrieves near-identical chunks, and those are deduplicated by `add_hits` — so
the pool grows by little, and what it does gain is more of the same. The loop
is mechanically perfect and semantically inert.

**The honest framing for Chapter 4:** what C4 demonstrates is not agentic
reasoning. It is *query reformulation with a stopping criterion*. Claiming
"agentic planner–executor with iterative retrieval" against this evidence
overstates what the model did. The mechanism is real and the plumbing works;
the intelligence the mechanism was built to exploit is not present in a 7B
quantized model at this prompt.

### 24.4 C4 makes out-of-scope questions worse

`q17` (Mumbai weather) and `q18` (Prime Minister of India) are deliberately
unanswerable from a college corpus. Both are the two slowest questions in the
run — **288.5 s and 281.5 s against a 214.6 s median** — because the agent kept
searching for material that cannot exist. q18 spent its entire three-round
budget on it.

The answers are effectively identical to C3's; q18's is word-for-word the same.
So the agent paid maximum cost for zero difference, on precisely the questions
where a human would stop immediately.

This is a real and reportable weakness of the agentic approach: **an agent that
cannot conclude "this corpus does not contain this" will always spend its full
budget on out-of-scope questions.** Worth a line in Chapter 5, and worth
considering as C5's job — a verification step that recognises an unanswerable
question is more valuable here than another retrieval.

### 24.5 A metric of mine that flattered the result

The tally I added to the harness first reported "iterated as intended: 15/20,
degraded towards C3: 5/20". That was wrong in a way worth recording, because it
is the exact failure this project keeps guarding against — a right-looking
number over the wrong quantity.

It counted `model_says_ready` as success. But READY on round one means **no
follow-up ever ran**: that is C3's behaviour plus one wasted LLM call, and it
happened on 8 of 20 questions. The metric scored 75% for a run whose
outcome-level effect was 10%.

The harness now reports the iteration distribution instead, and a new
`--compare` flag answers the question that actually matters — did the extra
retrieval reach the answer:

```bash
python3 run_baseline_eval.py --config C4 --compare C3
```

### 24.6 What this means for the project

This is a **negative result, and a good one.** It is specific, mechanistically
explained, and reproducible — a stronger Chapter 4 contribution than an
unexplained improvement would have been. The ablation did its job: it isolated
one change and showed that change does almost nothing, which is only possible
because every other variable was held fixed.

Three ways forward, in ascending cost:

1. **Report it as measured.** C4 adds cost and changes 2/20 outcomes; the
   follow-up queries are rephrasings; here is the evidence. Honest, complete,
   costs nothing further.
2. **Improve the decide prompt and re-run C4.** Give it few-shot examples of a
   gap-targeting follow-up versus a rephrasing, and have it name the missing
   fact before proposing a query. ~70 minutes per re-run. Might convert the
   mechanism into a real gain — and if it does not, that is a stronger finding
   still, because it shows the limit is the model rather than the prompt.
3. **Reconsider what C4 should be.** If the 7B model cannot decompose a
   question, the iterative-retrieval idea may need a different trigger — for
   example, iterating only when the reranker's top score falls below a
   threshold, which needs no reasoning at all.

Not chosen unilaterally: option 2 changes what C4 *is*, and the current results
are already a valid, defensible chapter.
