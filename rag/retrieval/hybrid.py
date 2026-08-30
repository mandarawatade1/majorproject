"""C2's retriever: dense and BM25 in parallel, fused with Reciprocal Rank Fusion.

Neither arm's ranking is touched by this class -- it only combines two
independently correct rankings into one. RRF is used instead of a weighted
score average because dense cosine similarity and BM25 scores live on
incomparable scales; averaging them would let whichever metric happens to
have larger raw magnitudes quietly dominate the fusion.

This is specifically the fix for a real, verified gap in C0/C1: a chunk that
answers a question in terse, keyword-dense form (a bullet list of
accreditation facts, for instance) can rank far outside a dense retriever's
top-k, because a bullet list does not read as semantically similar to a
natural-language question even when it contains the exact answer. BM25 scores
that same chunk highly on literal term overlap; RRF lets either arm's high
rank pull a chunk into the final result.
"""

from __future__ import annotations

from typing import Any

from rag.embedding.base import Embedder
from rag.indexing.base import IndexedHit, VectorIndex
from rag.indexing.bm25 import BM25Index
from rag.retrieval.base import RetrievalResult, stage_timer


def reciprocal_rank_fusion(
    ranked_lists: list[list[IndexedHit]], k: int = 60
) -> list[IndexedHit]:
    """Combine multiple rankings by rank position, not by raw score.

    Each hit's contribution is 1 / (k + rank). A chunk near the top of
    *either* list scores well; one near the top of both scores best of all.
    `k` dampens how much rank 1 outweighs rank 2 -- 60 is RRF's usual default
    and matches PipelineConfig.rrf_k, so C2's behaviour is exactly what the
    config declares, not a hidden second constant.
    """
    scores: dict[str, float] = {}
    best_hit: dict[str, IndexedHit] = {}

    for ranked in ranked_lists:
        for rank, hit in enumerate(ranked, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
            if hit.chunk_id not in best_hit:
                best_hit[hit.chunk_id] = hit

    ordered_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    fused: list[IndexedHit] = []
    for cid in ordered_ids:
        hit = best_hit[cid]
        fused.append(
            IndexedHit(
                chunk_id=hit.chunk_id,
                content=hit.content,
                score=scores[cid],
                metadata=hit.metadata,
            )
        )
    return fused


class HybridRetriever:
    """Dense + BM25 in parallel, fused with RRF."""

    name = "hybrid"

    def __init__(
        self,
        index: VectorIndex,
        sparse_index: BM25Index,
        embedder: Embedder,
        dense_top_k: int = 20,
        sparse_top_k: int = 20,
        rrf_k: int = 60,
        include_demo_sources: bool = True,
    ) -> None:
        self.index = index
        self.sparse_index = sparse_index
        self.embedder = embedder
        self.dense_top_k = dense_top_k
        self.sparse_top_k = sparse_top_k
        self.rrf_k = rrf_k
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
            dense_hits = self.index.search(vector, top_k=self.dense_top_k, where=where)

        with stage_timer(result, "sparse_search"):
            sparse_hits = self.sparse_index.search(
                query, top_k=self.sparse_top_k, where=where
            )

        with stage_timer(result, "fuse"):
            fused = reciprocal_rank_fusion([dense_hits, sparse_hits], k=self.rrf_k)

        result.dense_hits = dense_hits
        result.sparse_hits = sparse_hits
        result.fused_hits = fused[:top_k]
        result.hits = result.fused_hits
        return result


__all__ = ["HybridRetriever", "reciprocal_rank_fusion"]
