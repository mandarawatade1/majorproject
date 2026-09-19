# The self-describing chunk: one assumption, three defects

*Draft for Chapter 5. Every figure below was measured on the corpus and index
described; none is estimated. Rankings were recomputed directly from the
persisted BM25 index rather than inferred from answers.*

## The assumption

The retrieval pipeline was designed against a corpus of 773 HTML pages, and it
inherited an assumption from that corpus which was never written down: **that a
chunk's body text describes itself.**

For HTML this holds. A page about the Mechanical department says "Mechanical"
in its opening sentence, its headings, its links and its footer. The body
carries its own topic, so a retriever can find the page from the body alone.
Under that assumption the document title and section path are needed only to
*cite* a passage after it has been found, not to find it. The `Chunk` record
therefore carried `document_title` and `section_path` as citation metadata, and
`IndexedHit` carried them in a metadata dictionary.

Six syllabus PDFs were then added to the corpus:

| Document | Pages | Extracted |
|---|---|---|
| B.Tech Mechanical Engineering, Scheme with Syllabus (AY 2026-27) | 284 | 733 KB |
| B.Tech Information Technology Syllabus (NEP 2020) | 190 | 432 KB |
| B.Tech Automobile Engineering (Admission Year 2023-24) | 138 | 301 KB |
| B.Tech Electronics & Computer Science Syllabus | 75 | 126 KB |
| B.Tech Computer Engineering Curriculum (FY 2025-26) | 21 | 37 KB |
| S.Y. EXTC Scheme | 2 | 3.8 KB |

A syllabus table's body is course codes and integers:

```
MATH 101 Engineering Mathematics I    BSC  3 0 3 0 3
PHY 101  Engineering Physics          BSC  2 1 2 0.5 2.5
CHEM 101 Engineering Chemistry        BSC  2 1 2 0.5 2.5
```

The only text identifying this as B.Tech Mechanical Engineering, Semester I is
the heading — which lived in metadata, where no retriever could see it. The
chunk had stopped describing itself, and the assumption failed at every point
where it had been relied on.

## Defect 1 — the indexes never saw the header

`rag/indexing/chroma.py:114` embedded `chunk.content`; `rag/indexing/bm25.py:87`
tokenised `chunk.content`. Neither the document title nor the section path
entered the searchable text.

**Symptom.** For the question *"What subjects are in first year Mechanical
Engineering?"*, none of the Mechanical syllabus's 316 chunks appeared anywhere
in the 20 retrieved candidates. Retrieval returned the 2022 prospectus and a
Ph.D. programme overview.

**Fix.** A `Chunk.embed_text` property prefixing `title > section path` to the
body, used for embedding and BM25 tokenisation. The stored content remains the
section body verbatim, so citations and page provenance are unaffected.

**Effect.** Four syllabus chunks entered the candidate pool, at ranks 7, 9, 11
and 15.

## Defect 2 — the reranker never saw it either

`rag/reranking/cross_encoder.py:49` scored `(query, hit.content)`. A
cross-encoder trained on natural-language passage relevance was asked to judge
a table of course codes against a question naming a department the table never
spells out.

**Symptom.** All four syllabus chunks were eliminated. The five passages passed
to the generator were:

| Rank | Score | Passage |
|---|---|---|
| 1 | 2.89 | PCE Prospectus 2022, page 53 |
| 2 | 2.25 | Program Overview — Ph.D. in Mechanical Engineering |
| 3 | −0.64 | PCE Prospectus 2022, page 54 |
| 4 | −0.81 | *15 Best Mechanical Engineering Project Ideas in 2025* |
| 5 | −0.82 | PCE Prospectus 2022, page 45 |

A marketing blog post outranked the department's own syllabus. Only two scores
are positive: the reranker judged nothing else relevant, which was a correct
judgement given what it was shown.

**Fix.** An `IndexedHit.search_text` property rebuilding the same header from
the metadata already carried on every hit, and used for the reranking pair. A
shared `context_header()` helper is used by both properties so the text the
indexes are built from and the text the reranker judges cannot drift apart.

**Effect.** The blog post dropped out; a syllabus chunk entered the final five
at rank 3, score −0.36 — retrieved, but still ranked below prose.

## Defect 3 — no stopword removal on the query

`rag/indexing/bm25.py` tokenised with `_TOKEN_RE = [a-z0-9]+` and nothing else,
on the standard reasoning that BM25's IDF term downweights common words
automatically.

That reasoning holds for a diverse corpus. This corpus is single-institution.
Document frequencies over 4,114 chunks:

| Term | Chunks containing it |
|---|---|
| `of` | 2,759 |
| `in` | 2,398 |
| `engineering` | 1,930 |
| `mechanical` | 839 |
| `are` | 686 |
| `semester` | 589 |
| `i` | 546 |
| `what` | 110 |

"Engineering" and "mechanical" appear so widely that IDF barely separates
anything, and the residual weight of `what`, `are`, `in` and `of` was enough to
decide near-ties in favour of whichever page repeated the department name most
often.

**Symptom.** For *"What subjects are in Semester I of Mechanical Engineering?"*,
BM25 ranked the correct Semester I table **11th**, behind a page titled *"The
best college experience!"* (rank 1) and *"PERKS of PILLAI"* (rank 8).

**Fix.** A query-side stopword filter, `_tokenize_query()`. Documents are not
filtered, so collection statistics — document frequency and average length —
are unchanged and no index rebuild is required.

**A negative result worth recording.** The first stopword list included `i` as
a pronoun. This made retrieval *worse*: the Semester I chunk fell from 11th to
35th, because `i` is also the roman numeral distinguishing Semester I from
Semester IV, VI and VIII across fourteen near-identical tables in one document.
Single letters carry meaning in a course catalogue.

| Query | Stopwords | Rank of the Semester I chunk |
|---|---|---|
| "…Semester I of Mechanical Engineering?" | none removed (as shipped) | 11 |
| "…Semester I of Mechanical Engineering?" | removed, including `i` | 35 |
| "…Semester I of Mechanical Engineering?" | removed, `i` retained | **2** |
| "…first year Mechanical Engineering?" | removed, `i` retained | 34 |

## The consequence that would have been worse than failure

Between defects 2 and 3, the pipeline reached a state where a syllabus chunk
*did* survive reranking — but the chunk that survived was **Semester VIII**
(page 18: Personal Financial Management, Entrepreneurship), with Semester VI
also present at page 14. The Semester I table on page 8 was still absent.

Had the generator used that context confidently, it would have answered a
first-year question with final-year subjects, correctly cited. Its actual
response — *"the context provided does not specify the exact subjects"* — was
the honest reaction to being handed the wrong semester. A system that produced
a fluent answer at that moment would have been more dangerous than one that
retrieved nothing.

## Measured outcome

A fixed question set (`rag/batchtest.py`, 20 scored questions plus 2 controls)
measures whether the passage known to contain the answer reaches the five
chunks the generator is shown. It stops before generation, which takes minutes
per question and tests a different property.

**The metric was revised twice, both times to remove a structural unfairness
rather than an unwelcome result, and its final form was fixed before either
configuration was measured under it.**

- *Document level* — favoured C0, which produces 13,915 chunks against C1-C5's
  4,170 and therefore has three times as many chances that one chunk of a given
  document ranks.
- *Section metadata* — favoured C1-C5. C0's fixed chunker sets
  `section_path=None` by design, so it could not satisfy the test at all.
- *Passage text* — the question both chunkers can be asked on equal terms: does
  the text handed to the generator contain the answer? C0 passes one syllabus
  question under it, so it is not rigged against C0.

### The ablation

Scored on the chunks that reach the generator — `AssembledContext.sources`,
after the 8,000-character budget has been applied — so every configuration is
asked the same question.

| | Score | Chunks shown | Dropped at budget | Retrieved but not shown |
|---|---|---|---|---|
| **C0** naive: fixed 512-char windows, dense-only, top-5 | 14/20 | 5.0 | 0 | 0 |
| **C1** + structure-aware chunking | 17/20 | 4.5 | 11 | 1 |
| **C2** + hybrid dense/BM25 with RRF, top-20 | 18/20 | 8.0 | 263 | 1 |
| **C3** + cross-encoder reranking to top-5 | 19/20 | 4.7 | 7 | 0 |
| **C5** + post-answer claim verification | 19/20 | 4.6 | 9 | 0 |

Each step contributes through a different mechanism, and each is visible in the
instrumentation rather than inferred from the score.

**C0 → C1 (+3), chunking.** A 512-character window cuts a semester table away
from the heading that names it, so C0 retrieves the correct syllabus PDF and
the wrong window: for Semester I of Mechanical Engineering it returns that PDF
in two of its five slots and the Semester I table in none. Its single syllabus
pass, Semester V, is the case where the heading fell inside the window by
chance. Structure-aware chunking keeps heading and table together.

This step also introduces a cost. C1 retrieves the same five chunks as C0 but
shows 4.5, because structure-aware sections average 1,468 characters against
C0's fixed 512 and five of them can exceed the context budget. Keeping tables
whole and fitting passages into a fixed budget are in tension.

**C1 → C2 (+1), hybrid retrieval.** BM25 finds passages the dense arm ranks
below its top five. But C2 raises `dense_top_k` to 20 without any means of
choosing among them, and twenty chunks averaging 1,468 characters cannot fit in
8,000: **263 chunks were discarded at the budget across 22 questions**, twelve
per question. The Semester I question shows the consequence exactly — C2
*retrieves* the correct table and the budget discards it before the generator
sees it.

**C2 → C3 (+1), reranking.** The cross-encoder's contribution is not finding
better passages; C2 had already found the right one. It is deciding which of
the twenty found passages survive a fixed budget. Reranking to five returns the
context to 4.7 chunks and 7 drops, and the Semester I table is kept. Retrieval
and selection are separate jobs, and C2 performs the first without the second.

**C3 → C5 (0), verification.** C5 scores identically to C3, which is the
correct result rather than a null one: claim verification runs *after*
generation and cannot change which passages were retrieved. Its value, if any,
lies in detecting unsupported claims in the answer, which this measurement does
not examine. Reporting it as a flat step is what shows the harness is measuring
retrieval and only retrieval.

### Where the benefit is concentrated

| | Questions | C0 | C3 |
|---|---|---|---|
| Structured PDF tables | 7 | 2 | 6 |
| HTML prose | 13 | 12 | 13 |

**On prose, naive RAG is sufficient**: fixed-window, dense-only retrieval scores
12/13 against the full pipeline's 13/13. The entire measured benefit of
structure-aware chunking, hybrid search and reranking is concentrated in
documents whose meaning depends on structure the body text does not restate.

This bounds the claim in a way an unqualified improvement figure would not. On
a corpus of ordinary web pages, the additional machinery — a second index, a
fusion step, and roughly 4.7 seconds of cross-encoder inference per query —
would have bought approximately nothing.

### A note on an earlier figure

An initial document-level run scored C3 at 20/20. That figure is superseded and
should not be quoted. One of those passes -- *"What subjects are in first year
Mechanical Engineering?"* -- was a match on the right document at the wrong
semester, which is the failure this project has elsewhere identified as more
dangerous than retrieving nothing. Under passage-level matching it is correctly
scored as a miss, and C3 stands at 19/20.

Retrieval is deterministic: no sampling occurs in the embedder, BM25, the
fusion step or the cross-encoder, and repeated runs return identical results.

## What the fixes do not address

**Retrieval has no concept of "not found".** Two control questions ask for the
fees of programmes absent from the corpus:

```
"fee for B.Tech Artificial Intelligence and Data Science?"
   → Computer Engineering fees | ECE fees | EXTC fees

"fee for B.Tech Fashion Design?"
   → ECE fees | EXTC fees | Computer Engineering fees
```

Retrieval always returns its nearest five neighbours, however distant. The only
safeguard against a fabricated figure is the generator noticing that the
department it was asked about is not the department it was given.

**Institutional vocabulary is not handled.** *"What subjects are in first year
Mechanical Engineering?"* fails at every configuration. "First year" and
"Semester I" share no tokens, so BM25 contributes nothing; and the mapping
between them is an institutional convention that a general-purpose embedder
(`BAAI/bge-small-en-v1.5`, trained on general web text) has no reason to have
learned. The same applies to FE, SE, TE and BE. Retrieval returns the correct
document and the wrong semester, which is the more dangerous of the two
possible failures.

Two remedies are available and were not applied. The question can be rewritten
to match the documents, by a synonym table or by the C4 planner. Alternatively
the documents can be enriched to match the questions, by writing
`Semester I (First Year)` into the section header at index time -- which
addresses both the dense and sparse arms at once and requires no query-time
logic, but only for phrasings anticipated in the header.

**Citation enforcement guarantees a marker, not evidence.** Asked for the
Computer Engineering fee, the system answered `₹3,50,000 Per Year [S4]`. The
figure is correct and its wording matches S1 exactly. S4 contains no fee at
all — 738 characters of programme description. The right answer pointed at the
wrong source, and the affordance meant to make the answer checkable is the part
that failed.

**Near-duplicates crowd the context.** The five university department pages
differ mainly in one figure, and on a fee question they occupied all five
context slots. Duplicate sections compound this: the parser emits page 8 of the
Mechanical syllabus twice (headings `Semester I` and `(Admitted in 2026-27)`,
1,593 characters each) and page 14 three times.

## Why none of this was detected earlier

The evaluation was computed before the syllabus PDFs entered the corpus. Every
question in the evaluation set was answerable from HTML prose, so the failure
could not appear in it: the corpus that exposes the defect did not exist when
the numbers were produced.

At runtime nothing appeared wrong. Retrieval returned twenty passages.
Reranking returned five. The generator produced a fluent, well-cited answer.
Every stage reported success. The only evidence of failure was the *content* of
the answer, which no component inspects.

This is the same shape as the other defects found in this project: a signing-key
guard checking a placeholder string that nothing used; a seeder that reports
documents loaded and never removes any; a parser that counts what it kept and
says nothing about what it discarded; and a `--only-seeds` crawl flag that
suppressed sitemap expansion while breadth-first link-following continued
unchanged, so a run seeded with three URLs fetched 39 pages.

In every case a component reported what it did and stayed silent about what it
failed to do, and the absence remained invisible until two independent accounts
of the same thing were compared. Here that comparison was a diagnostic harness
printing retrieval's own ranking, held against the corpus text read directly
from disk.
