"""C0's retriever: dense similarity, top-k, nothing else.

No query rewriting, no sparse arm, no fusion, no reranking. Whatever the
embedding model ranks highest is what the generator sees. This is the behaviour
every later configuration is measured against, so it is implemented carefully:
a baseline that is worse than a naive implementation would honestly be inflates
every improvement claimed on top of it.
"""

from __future__ import annotations

from typing import Any

from rag.embedding.base import Embedder
from rag.indexing.base import VectorIndex
from rag.retrieval.base import RetrievalResult, stage_timer


class DenseRetriever:
    name = "dense"

    def __init__(
        self,
        index: VectorIndex,
        embedder: Embedder,
        include_demo_sources: bool = True,
    ) -> None:
        self.index = index
        self.embedder = embedder
        self.include_demo_sources = include_demo_sources

    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        result = RetrievalResult(query=query)

        where: dict[str, Any] | None = None
        if not self.include_demo_sources:
            where = {"is_demo": False}
        result.filters_applied = dict(where or {})

        with stage_timer(result, "embed_query"):
            vector = self.embedder.embed_query(query)

        with stage_timer(result, "dense_search"):
            hits = self.index.search(vector, top_k=top_k, where=where)

        result.dense_hits = hits
        # C0 has no fusion and no reranking, so the dense hits are the final
        # hits. The other lists stay empty, which is exactly what distinguishes
        # a C0 row from a C2 row in retrieval_logs.
        result.hits = hits
        return result
