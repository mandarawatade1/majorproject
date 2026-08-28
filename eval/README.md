# Evaluation harness (`eval/`)

Empty in Phase 0. Built in Phase 10.

Contains the RAGAS harness, the LLM-as-a-judge rubric, and the Streamlit
console used to run ablations and export figures for Chapter 4 of the report.

## Why Streamlit is here and not in the portal

The survey paper names Streamlit as the interface. The portal itself is
Next.js (see architecture-plan.md section 0.3, Deviation A), so Streamlit is
scoped to what it is genuinely good at: an internal console for running
experiments and staring at metric tables. The stack stays truthful to the
paper and the portal stays production-shaped.

## Metrics

| Metric | Source | Measures |
|---|---|---|
| Faithfulness | RAGAS | Is every claim supported by retrieved context? |
| Answer Relevancy | RAGAS | Does the answer address the question asked? |
| Context Precision | RAGAS | How much retrieved context was actually useful? |
| Context Recall | RAGAS | Was all the needed context retrieved? |
| Hit Rate@k, MRR, nDCG@k | custom | Retrieval quality, independent of generation |
| Correctness / completeness / coherence / citation quality | LLM judge | Qualitative, 1-5 scale |

The judge model is deliberately from a different family than the generator.
A model grading its own output inflates the scores and is not defensible.

## Configurations compared

`C0` naive baseline -> `C1` +structure-aware chunking -> `C2` +hybrid retrieval
-> `C3` +reranking -> `C4` +agentic layer -> `C5` +verification (full system).

Report mean +/- std over 3 runs, with latency alongside accuracy so the
trade-off is stated honestly.
