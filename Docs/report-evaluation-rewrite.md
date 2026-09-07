# Replacing the four RAGAS commitments

*Draft. Nothing has been changed in `Report final (1).docx`.*

## The principle

Chapter 2's RAGAS passages describe prior work and are accurate — they stay.
These four say **this project** will use RAGAS, and it doesn't. Each
replacement describes the evaluation that was actually run, and gives the
reason the RAGAS library itself was not used, so the difference reads as a
decision rather than an omission.

That reason is real and worth stating plainly: **RAGAS's reference
implementation defaults to a hosted commercial judge model.** Running it as
shipped would have broken the project's own open-source, no-paid-API
constraint at the evaluation step — the exact mistake §5 of the plan warns
about. Faithfulness is therefore computed by a verification stage running on a
local model. Answer Relevancy and Context Precision were not computed, and the
replacements no longer claim them.

---

## ¶176 — Objectives, Chapter 1

**Current**

> Comprehensive System Evaluation: To measure performance using the RAGAS
> framework (Faithfulness, Answer Relevancy, and Context Precision) and an
> LLM-as-a-judge evaluation protocol.

**Proposed**

> Comprehensive System Evaluation: To measure performance through a controlled
> ablation across seven pipeline configurations answering a fixed question set,
> reporting retrieval and generation latency, citation and grounding behaviour,
> and claim-level faithfulness. Faithfulness is computed by a post-answer
> verification stage running on a locally hosted model rather than through the
> RAGAS reference implementation, whose default judge requires a commercial API
> and would breach this project's open-source constraint at the evaluation step.

---

## ¶184 — Chapter outline, Chapter 1

**Current**

> Chapter 4: Implementation and Results evaluates the framework using the RAGAS
> metrics of faithfulness, answer relevancy, and context precision against
> conventional baselines.

**Proposed**

> Chapter 4: Implementation and Results evaluates the framework by ablation,
> comparing a naive baseline against configurations that add structure-aware
> chunking, hybrid retrieval, cross-encoder reranking, agentic retrieval and
> post-answer verification in turn. For each configuration it reports retrieval
> and generation latency, citation behaviour, and the proportion of generated
> claims supported by the retrieved context.

---

## ¶296 — Proposed Methodology, Chapter 3

**Current**

> For evaluation, the system should be assessed using the RAGAS framework,
> focusing on key metrics such as Faithfulness, Answer Relevancy, and Context
> Precision to measure the quality and reliability of responses. These
> quantitative evaluations should be complemented with an LLM-as-a-judge
> approach to provide qualitative assessment of answer correctness and
> coherence[15]. This combined evaluation strategy ensures a comprehensive
> analysis of system performance in terms of accuracy, relevance, and
> trustworthiness.

**Proposed**

> For evaluation, the system is assessed by ablation: each retrieval and
> reasoning capability is placed behind a configuration flag so that it can be
> enabled in isolation, and every configuration answers the same fixed question
> set. This isolates the contribution of each stage rather than reporting a
> single aggregate score for the finished system. Faithfulness — whether each
> generated claim is supported by the retrieved context — is measured directly
> by a post-answer verification stage using a locally hosted model, so the
> evaluation depends on no commercial service. Retrieval quality is assessed
> through the ablation itself, by what each configuration retrieves and cites
> for the same question.

---

## ¶300 — Proposed Methodology, Chapter 3

**Current**

> To reduce hallucinations and improve reliability, the system incorporates
> retrieval-grounded generation, citation enforcement, and post-answer
> verification techniques. Additionally, evaluation is performed using the
> RAGAS framework, focusing on metrics such as Faithfulness, Answer Relevancy,
> and Context Precision, along with LLM-based evaluation for qualitative
> assessment. Together, these techniques ensure a robust, accurate, and
> scalable knowledge management system.

**Proposed**

> To reduce hallucinations and improve reliability, the system incorporates
> retrieval-grounded generation, citation enforcement, and post-answer
> verification. Verification decomposes each answer into its individual claims
> and checks each against the retrieved passages, flagging any that are not
> supported and withholding answers that are wholly unsupported. Because this
> check runs on the same locally hosted model family as generation, the
> reliability measurement inherits no external dependency. Together these
> techniques give a system whose answers can be traced to their sources and
> whose unsupported claims are identified rather than presented alongside
> supported ones.

---

## What this commits you to putting in Chapter 4

Each of these is already in your data — nothing here promises new work.

| Claim | Evidence you hold |
| --- | --- |
| Seven configurations, fixed question set | `eval/results/C0…C5` + C1-CONTROL, 20 questions each |
| Latency per stage per configuration | `summary.csv` in every run directory |
| Citation behaviour | `comparison.csv` — citations, with_section, demo_cited |
| Claim-level faithfulness | C5 verification: 17 of 48 claims flagged, 0 unparseable |
| Ablation isolates one variable per step | `PipelineConfig`, and the C1-CONTROL run added for exactly this |

## Two things to add while you are in here

**The variance finding.** Three identical requests to the live system produced
three different citations for the same correct fact. Chapter 4 should say that
each configuration was run once per question, and that repeated runs have
produced different citations — so the reported figures describe those runs
rather than the system's expected behaviour. Stating this is worth more than
the tidiness it costs; an examiner who spots it unaided will wonder what else
went unchecked.

**LLM-as-a-judge.** It is dropped from all four paragraphs above because it was
never run. `llama3.1:8b` was pulled and deliberately reserved as an evaluation
judge, and kept out of the system so that judge and generator were never the
same model. If you want to keep the idea in the report, the honest place is
Future Work: *"a second model was reserved as an independent judge; scoring
correctness and coherence with it remains future work."*
