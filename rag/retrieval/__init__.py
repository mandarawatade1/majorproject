"""Retrieval strategies.

`DenseRetriever` is C0's. `HybridRetriever` (Phase 4, C2) adds BM25 and RRF
fusion behind the same `Retriever` protocol. A cross-encoder reranker (C3)
follows the same pattern.
"""

from rag.retrieval.base import RetrievalResult, Retriever
from rag.retrieval.dense import DenseRetriever
from rag.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion

__all__ = [
    "DenseRetriever",
    "HybridRetriever",
    "RetrievalResult",
    "Retriever",
    "reciprocal_rank_fusion",
]
