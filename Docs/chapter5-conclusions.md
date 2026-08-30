# Chapter 5 — Conclusions, Limitations and Future Work

Working draft. Every claim below is traceable to `Docs/architecture-plan.md`
(section numbers given) or to `eval/results/`. Nothing here is asserted without
a measurement behind it.

---

## 5.1 What was built

A retrieval-augmented question answering system for Pillai College of
Engineering, running entirely on open-source components with no external API
calls: a 765-document corpus crawled from the institution's public website and
supplemented with clearly-labelled synthetic documents, a PostgreSQL data
layer, ChromaDB and BM25 indexes, and a generation stage using
`qwen2.5:7b-instruct-q4_K_M` served locally by Ollama.

The system exists in six configurations, C0 through C5, each adding exactly one
capability to the previous one, plus one control configuration. All seven were
evaluated on the same 20-question set against the same corpus.

A FastAPI service exposes the system as a streaming chat endpoint and a set of
portal read endpoints.

---

## 5.2 Contributions

**1. A single-variable ablation, and the discipline to keep it single-variable.**

The comparison was designed so that C0 and C5 run the same orchestrator over
the same corpus with the same prompt assembly, differing only in the stages a
configuration object selects. This is stricter than the common practice of
writing a "baseline" and a "proposed system" as separate programs, where a
measured difference includes every incidental difference in how each was
written.

Maintaining that property required correcting the design mid-project. An audit
found that C1 changed the chunker *and* the system prompt, so a C0 → C1 result
could not be attributed to either (§20.2). A control configuration was added to
separate them. A second audit found that the C0 results had been collected
against the wrong index entirely, making the first ablation step measure the
prompt rather than the chunker (§22); this was detected because C0 and C1 cited
byte-identical sources on 20 of 20 questions, and because 60 of C0's 88
citations carried a section path that C0's chunker cannot produce.

**2. Structure-aware chunking is what makes page-level citation possible.**

The naive baseline produces **zero** citations carrying a section or page
reference — not through omission, but because a fixed 512-character window
belongs to no section of a document. From C1 onward, 60 of 88 citations carry a
section and, where the source is a PDF, a page number. The project's
page-level provenance requirement is delivered by the chunker, not by the
prompt (§4.2).

**3. Cross-encoder reranking suppresses synthetic content.**

C2, which retrieves 20 passages with no reranking, cited demo documents 20
times out of 115 (17%). C3 adds a cross-encoder and that falls to 5 of 80 (6%).
The synthetic corpus is deliberately written as plausible institutional prose,
so it competes well on embedding similarity and on keyword overlap; a
cross-encoder scoring the (query, passage) pair jointly rejects it. This
benefit is invisible to the standard retrieval metrics (§4.2).

**4. A negative result about agentic retrieval, with a mechanism.**

C4 adds an iterative retrieve-decide loop. It ran at least one follow-up search
on 13 of 20 questions and averaged 1.95 iterations — the mechanism works. But
it changed the evidence actually handed to the generator on **2 of 20**
questions, and neither change was an improvement.

The cause is specific and observable: **all 12 follow-up queries were
rephrasings of the original question**, not searches for a missing fact,
despite an instruction explicitly forbidding this. A rephrased query embeds
close to the original, retrieves near-identical passages, and those are
deduplicated away. What C4 demonstrates is query reformulation with a stopping
criterion, not agentic reasoning (§24).

**5. A positive result about verification, from the same model — and the
contrast between them.**

C5 adds a post-generation check. It flagged 17 unsupported claims across 48
judged, correctly identified fabricated content on all four cases of a
controlled probe including one requiring two sentences of the same answer to be
judged differently, and produced **zero unparseable verdicts**.

The pairing is the strongest claim in this work. C4 and C5 use the same model,
the same quantization, the same one-line output contract and the same prompt
discipline. Asked to **plan** — decompose a question, name a missing fact — it
failed 12 times out of 12. Asked to **check** — does this sentence follow from
this passage — it succeeded. The difference is not prompt quality or effort but
the kind of task: planning requires generating something not present, checking
requires comparing two things that are. For a 4-bit quantized 7B model the
second is tractable and the first is not.

**6. Plain-text contracts are reliable where structured output is not.**

Structured output (JSON, tool-calling) was rejected at design time as
unreliable for this model class. A constrained one-line reply was used instead,
for both C4's decide step and C5's verifier. Across the full evaluation this
parsed correctly on **59 consecutive questions with zero failures**. This is the
most transferable engineering result here, and it generalises beyond this
system.

---

## 5.3 Limitations

Stated in descending order of how much they constrain the conclusions.

**1. Verification checks grounding, not attribution.**

This is the most important limitation, and it was found by using the system
rather than by evaluating it. Asked for the Computer Engineering intake, the
system answered:

> "The intake for Computer Engineering at Pillai College of Engineering is 180
> students **[S1]**."

The figure is correct. But [S1] was the *Master of Technology* table, which
states an intake of 12; the 180 figure is in [S2], the *Bachelor of Technology*
table. Run under C5, verification returned **supported, support rate 1.0**.

That verdict is correct by C5's definition: it asks whether a sentence is
supported by the retrieved context, and 180 *is* in the context. It was never
asked whether the citation marker points at the passage the fact came from.

So the property established is narrower than "the citations are correct":

* C5 verifies **grounding** — is this claim supported somewhere in the context?
* C5 does not verify **attribution** — does this citation point at the passage
  that supports it?

A misattributed citation is arguably the most damaging error available to a
system whose central promise is traceability. It looks authoritative, it
survives verification, and it is wrong only to a reader who follows it.

Neither the evaluation harness nor RAGAS's faithfulness metric can detect this,
because both score claims against the retrieved context as a whole. It became
visible only when an answer was rendered alongside its sources in an interface
(§28.3).

**2. Twenty questions, one run each, at a non-zero temperature.**

The evaluation set is 20 questions written by the project team — a small sample
with the selection bias any internal evaluation carries. More seriously,
generation runs at temperature 0.1, and two runs of the same question under C4
were observed to retrieve byte-identical passages and produce materially
different answers. Any difference between configurations smaller than the
run-to-run variation is not evidence (§23.4).

**3. Latency is not reliably measurable on the evaluation hardware.**

The same command, run three times within minutes, produced decide-step timings
of 4.1 s, 59.2 s and 5.9 s. The machine holds a 7B model, a cross-encoder, an
embedding model, ChromaDB and PostgreSQL simultaneously and is memory-bound.
Cost is therefore reported in LLM calls, which are structural and reproducible,
rather than seconds (§23.3, §4.4).

**4. The C1 → C2 step changes two things.**

C2 enables hybrid retrieval *and* raises the retrieved passage count from 5 to
20, so it assembles context from more passages than C1 did. Across the sequence
the context width goes 5 → 20 → 5. That row measures retrieval strategy and
context width together, and is the one remaining confound in the ablation
(§20.7).

**5. C5 can withhold a single-sentence answer on one model judgment.**

Both refusals in the final C5 run were one-sentence answers. The safeguard that
protects hedged multi-sentence answers — requiring the answer to consist
entirely of unsupported claims — offers no protection when there is only one
sentence. Whether those two refusals were correct cannot be determined from the
saved artifacts, because the harness records chunk identifiers but not chunk
text (§26.3).

**6. Retrieval is degraded by two properties of the corpus.**

Faculty profile pages list degrees held ("M.E. Computer Engineering"), so they
compete strongly on both dense and sparse retrieval for programme questions; on
one eligibility question the cross-encoder ranked a faculty page above the
prospectus. Separately, boilerplate navigation content produces near-identical
embeddings across unrelated pages — eight documents were observed sharing a
cosine score to six decimal places. Both are corpus properties rather than
architectural ones (§23.6).

**7. Chunk identifiers are not stable across runs.**

They are generated per run, so re-indexing cannot update in place and the dense
and sparse indexes only share identifiers when built in the same process. This
is now guarded rather than fixed (§21.5).

---

## 5.4 Future work

**1. Attribution checking — the direct successor to C5.**

Give the verifier, for each sentence, only the passages that sentence actually
cites, and ask whether *those* support it. This converts grounding checking
into attribution checking and addresses §5.3.1 directly. It is a capability
change rather than a repair: it alters what the verifier measures and would
require re-collecting the C5 results.

**2. Record the assembled context alongside each result.**

The harness saves chunk identifiers but not chunk text, which is why two
refusals could not be adjudicated after the fact. Saving the context would make
this class of question decidable rather than arguable, at negligible cost.

**3. Repeated runs, or temperature zero.**

Either would remove sampling noise from the comparison. Repeated runs are
preferable, since they also quantify the variance rather than hiding it.

**4. A larger and externally-sourced evaluation set.**

Questions drawn from actual enquiries to the institution — admissions email,
for instance — would remove the selection bias of a team writing its own test.

**5. Deterministic chunk identifiers.**

Deriving the identifier from document, position and content hash would make
re-indexing idempotent and make the dense and sparse indexes agree by
construction, removing the operational hazard §5.3.7 currently guards against.

**6. Improve or replace C4's decide step.**

Two directions. Give the model few-shot examples contrasting a gap-targeting
follow-up with a rephrasing, and re-measure — if it still rephrases, that is a
stronger claim about the model's limits than the current result. Or abandon
LLM-driven iteration and trigger a second retrieval on a measurable signal, such
as the reranker's top score falling below a threshold, which requires no
reasoning at all.

**7. Corpus curation for retrieval.**

Excluding boilerplate regions and down-weighting faculty profile pages for
programme-level questions would address §5.3.6 without changing the
architecture.

---

## 5.5 Conclusion

The system meets its functional objective: it answers questions about the
institution from a locally-held corpus, with page-level citations, using only
open-source models, and it distinguishes real institutional content from
synthetic content at every layer from ingestion through to the rendered answer.

The research objective produced a more interesting result than expected. Of the
five claimed innovations, structure-aware chunking and reranking delivered
measurable, explicable benefits; hybrid retrieval changed what was retrieved on
every question; the agentic layer did almost nothing and it is now clear why;
and verification worked, while establishing a narrower property than the phrase
"answer verification" suggests.

That mixture is the honest outcome of an ablation that was built to isolate
variables and then held to that standard, including when doing so meant
discarding a set of results, adding a control configuration mid-project, and
publishing a negative result about the component that sounds most impressive.
A design that had reported uniform improvement across all five stages would
have been less informative and less likely to be true.
