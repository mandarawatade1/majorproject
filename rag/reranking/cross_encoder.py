"""C3's reranker: a cross-encoder rescoring C2's fused candidate set.

Dense and BM25 both score a chunk against a query independently of each
other, without ever looking at the query and the chunk together. A
cross-encoder does exactly that: it takes the (query, chunk) pair jointly and
produces a single relevance score, which is a strictly more informed judgment
than fusing two independent rankings -- at the cost of being too slow to run
over an entire corpus, which is why it only reranks C2's already-narrowed
top-N fused candidates, not the whole index.

`cross-encoder/ms-marco-MiniLM-L-6-v2` is used deliberately: it is small
(~80MB, CPU-friendly, no GPU required), which matches the project's 8GB-RAM
baseline hardware constraint from Report Table 3.1 the same way BM25 was
chosen over a heavier sparse method.
"""

from __future__ import annotations

from typing import Any

from rag.indexing.base import IndexedHit


class CrossEncoderReranker:
    """Rescores a candidate list jointly with the query; returns the top N."""

    name = "cross_encoder"

    def __init__(
        self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    ) -> None:
        self.model_name = model_name
        self._model: Any | None = None

    @property
    def model(self) -> Any:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(
        self, query: str, hits: list[IndexedHit], top_n: int
    ) -> list[IndexedHit]:
        if not hits:
            return []

        pairs = [(query, hit.search_text) for hit in hits]
        scores = self.model.predict(pairs)

        scored = sorted(
            zip(hits, scores, strict=True), key=lambda pair: pair[1], reverse=True
        )

        reranked: list[IndexedHit] = []
        for hit, score in scored[:top_n]:
            reranked.append(
                IndexedHit(
                    chunk_id=hit.chunk_id,
                    content=hit.content,
                    score=float(score),
                    metadata=hit.metadata,
                )
            )
        return reranked


__all__ = ["CrossEncoderReranker"]
