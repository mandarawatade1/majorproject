"""Knowledge service: the RAG pipeline.

Deliberately independent of FastAPI. The API layer imports this package; this
package never imports the API. That boundary is what lets the same pipeline be
driven from the web app, the CLI, and the evaluation harness — and it is what
makes the C0-C5 ablation comparison in the report a fair, single-variable one.

Module layout (architecture-plan.md section 6):

    ingestion/    crawler, PDF/HTML parsers, corpus manifest        [Phase 1]
    chunking/     structure-aware semantic chunker, low-info filter [Phase 4]
    enrichment/   metadata, summaries, hypothetical questions       [Phase 4]
    indexing/     Chroma dense index, BM25 sparse index             [Phase 4]
    retrieval/    query analysis, hybrid search, RRF, reranking     [Phase 4]
    agent/        LangGraph planner - executor - critic             [Phase 5]
    generation/   grounded prompting, citation assembly             [Phase 3]
    verification/ claim extraction and entailment checking          [Phase 5]
    config.py     PipelineConfig — the object that defines C0 to C5 [Phase 3]
"""

__version__ = "0.1.0"
