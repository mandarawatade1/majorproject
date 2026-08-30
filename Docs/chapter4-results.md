# Chapter 4 — Results

Working material for the results chapter. Every number below comes from
`eval/results/`, computed by the script recorded in `Docs/architecture-plan.md`
§28; `eval/results/comparison.csv` holds the same figures machine-readably.

Seven runs, 20 questions each, all against the same 765-document corpus, the
same embedding model (`BAAI/bge-small-en-v1.5`) and the same generator
(`qwen2.5:7b-instruct-q4_K_M`) at temperature 0.1.

---

## 4.1 The configurations

| Config | Adds | Chunking | Retrieval | Rerank | Agent | Verify |
| --- | --- | --- | --- | --- | --- | --- |
| C0 | naive baseline | fixed 512 | dense top-5 | – | – | – |
| C1-CONTROL | *control:* C1's chunking, C0's prompt | structure-aware | dense top-5 | – | – | – |
| C1 | + grounding prompt | structure-aware | dense top-5 | – | – | – |
| C2 | + hybrid retrieval (RRF) | structure-aware | dense 20 + BM25 20 | – | – | – |
| C3 | + cross-encoder reranking | structure-aware | dense 20 + BM25 20 | top-5 | – | – |
| C4 | + agentic iterative retrieval | structure-aware | as C3, up to 3 rounds | top-5 | ✓ | – |
| C5 | + post-answer verification | as C4 | as C4 | top-5 | ✓ | ✓ |

C1-CONTROL is not a stage of the proposed system. It exists because C1 changes
two things at once — the chunker *and* `enforce_citations`, which swaps the
system prompt — so without it a C0 → C1 difference could not be attributed to
either. See §20.2 and §27.

---

## 4.2 Retrieval behaviour

| Config | Citations | Carrying a section path | Citing demo data |
| --- | ---: | ---: | ---: |
| C0 | 100 | **0** | 6 |
| C1-CONTROL | 88 | 60 | 7 |
| C1 | 88 | 60 | 7 |
| C2 | 115 | 83 | **20** |
| C3 | 80 | 54 | 5 |
| C4 | 79 | 52 | 5 |
| C5 | 79 | 52 | 5 |

**Structure-aware chunking is what makes page-level citation possible at all.**
C0 produces zero citations carrying a section path, and this is not a defect:
`FixedSizeChunker` deliberately sets `section_path=None`, because a fixed
512-character window spans arbitrary parts of a document and belongs to no
section. Every citation C1 onward emits — 60 of 88 — carries a section and,
where the source is a PDF, a page. That is the project's page-level provenance
requirement, and it is delivered by the chunker rather than by the prompt.

**Reranking suppresses synthetic content.** C2, which retrieves 20 chunks and
has no reranker, cited demo documents 20 times out of 115 (17%). C3 adds the
cross-encoder and that falls to 5 of 80 (6%). The demo corpus is by design
plausible-looking institutional prose, so it competes well on embedding
similarity and on BM25; a cross-encoder scoring the *pair* rejects it. This is
a measurable benefit of reranking that the retrieval metrics alone do not show.

---

## 4.3 What each step changed

Final sources handed to the generator, identical between adjacent configs:

| Step | Identical | Interpretation |
| --- | ---: | --- |
| C0 → C1-CONTROL | 0/20 | chunking changes retrieval completely |
| C1-CONTROL → C1 | **20/20** | the prompt changes the *answer*, never the retrieval |
| C1 → C2 | 0/20 | hybrid retrieval changes what is found |
| C2 → C3 | 0/20 | reranking reorders and narrows |
| C3 → C4 | **18/20** | the agent changed the outcome on 2 questions |
| C4 → C5 | **20/20** | verification does not touch retrieval, by construction |

Two of these are confirmations rather than findings. C1-CONTROL → C1 at 20/20
proves the control isolates the prompt cleanly; C4 → C5 at 20/20 proves C5 adds
a check and nothing else. Both are what a correct ablation *should* produce, and
neither would be visible without the comparison.

**C3 → C4 at 18/20 is the substantive negative result** — see 4.5.

---

## 4.4 Cost

| Config | Retrieval (s) | Generation (s) | LLM calls per question |
| --- | ---: | ---: | ---: |
| C0 | 6.1 | 55.2 | 1 |
| C1 | 6.4 | 102.5 | 1 |
| C2 | 6.9 | 136.9 | 1 |
| C3 | 11.4 | 97.5 | 1 |
| C4 | 95.0 | 110.7 | up to 3 |
| C5 | 105.4 | 126.5 | up to 4 |

Reranking costs about 5 s per question (C2 → C3). The agent costs an order of
magnitude more — 11 s to 95 s — because each round adds a retrieval *and* an
LLM call to decide whether to continue. Verification adds a further ~99 s.

**State cost in LLM calls, not seconds.** Wall-clock on the evaluation machine
(8 GB, running Ollama, the cross-encoder, the embedding model, Chroma and
PostgreSQL together) varies by an order of magnitude with background load: the
identical command was measured at 4 s, 59 s and 6 s for the same step within a
few minutes (§23.3). The call counts are structural and reproducible; the
seconds are not. C2's mean wall time in particular is not comparable with the
others and should not be quoted.

---

## 4.5 C4: the agent iterates, and it does not help

| | |
| --- | ---: |
| Ran at least one follow-up search | 13/20 |
| No follow-up (identical to C3's behaviour) | 7/20 |
| Mean iterations | 1.95 |
| Final sources changed versus C3 | **2/20** |
| Unparseable decisions | **0/20** |

Stop reasons: `model_says_ready` 8, `iteration_cap` 7, `repeated_query` 5.

**Every one of the 12 follow-up queries was a rephrasing of the original
question**, not a search for a missing fact:

| Question | Follow-up chosen |
| --- | --- |
| What is the intake for Computer Engineering…? | *What is the intake for Computer Engineering at Pillai College…* |
| What entrance exams are accepted…? | *entrance exams accepted by Pillai College of Engineering* |
| What is the weather forecast for Mumbai this week? | *weather forecast mumbai this week* |

The decide prompt instructs the model, in as many words, to target the missing
fact and *not* rephrase. It ignored that on 12 of 12. This explains the 2/20
completely: a rephrased query embeds close to the original, retrieves
near-identical chunks, and those are deduplicated away, so the pool grows by
little and gains nothing the reranker prefers.

The honest description of C4 is therefore **query reformulation with a stopping
criterion**, not agentic reasoning. The mechanism works; the reasoning the
mechanism was built to exploit is not present in a 4-bit 7B model at this
prompt.

C4 also makes out-of-scope questions worse. The two unanswerable questions
(Mumbai weather, Prime Minister of India) were the two slowest in the run —
288 s and 281 s against a 215 s median — because the agent kept searching for
material that cannot exist in a college corpus.

---

## 4.6 C5: the same model checks well

| | |
| --- | ---: |
| Claims judged | 48 |
| Claims flagged unsupported | 17 |
| Mean support rate | 0.537 |
| Answers annotated with an unsupported-claim note | 13/20 |
| Answers withheld | 2/20 |
| Unparseable verdicts | **0/20** |

Verdicts: `partially_supported` 10, `unsupported` 5, `supported` 4, `skipped` 1.

**This is the paired finding, and it is the chapter's strongest claim.** C4 and
C5 use the same model, the same quantization, the same one-line output contract
and the same prompt discipline. C4 asked it to *plan* — decompose a question and
name a missing fact — and it failed on 12 of 12. C5 asked it to *check* —
does this sentence follow from this passage — and it flagged 17 claims across
48, correctly identifying fabricated content in a controlled probe on 4 of 4
cases including a mixed answer where only the invented sentence was flagged.

The difference is not effort or prompt quality. It is the *kind* of task.
Planning requires generating something that is not present; checking requires
comparing two things that are. For a small quantized model the second is
tractable and the first is not.

**Reliability of the plain-text contract.** Across C4's decide step and C5's
verifier, the one-line reply parsed correctly on **59 consecutive questions**,
with zero failures. Structured output (JSON, tool-calling) was rejected at
design time as unreliable for this model class; a constrained plain-text reply
proved reliable. This is the most transferable engineering result in the
project.

---

## 4.7 Threats to validity

**Generation is not deterministic.** `LLM_TEMPERATURE=0.1`. Two runs of the same
question under C4 retrieved byte-identical chunks and produced materially
different answers. Any difference drawn from a single run per configuration is
confounded with sampling noise. Accuracy differences smaller than the
run-to-run variation should not be claimed. (§23.4)

**C1 → C2 changes two things.** C2 raises `dense_top_k` from 5 to 20 and has no
reranker, so it assembles context from up to 20 chunks where C1 used 5. Across
the sequence, chunks-in-context goes 5 → 20 → 5. The C1 → C2 row therefore
measures retrieval strategy *and* context width together. (§20.7)

**C5 can withhold a one-sentence answer on a single judgment.** Both refusals
were one-sentence answers, where the "answer must be nothing but unfounded
claims" safeguard gives no protection. Whether those two were correctly
withheld cannot be determined from the saved artifacts, because the harness
records chunk ids but not chunk text. (§26.3)

**Latency is not reliably measurable on this hardware.** See 4.4.

**Twenty questions is a small sample**, and they were written by the project
team, which is a source of selection bias no internal evaluation escapes.
