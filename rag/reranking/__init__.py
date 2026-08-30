"""Reranking strategies.

`CrossEncoderReranker` (Phase 4, C3) rescores C2's fused top-N candidates
jointly with the query, which neither the dense nor the BM25 arm can do on
their own.
"""

from rag.reranking.cross_encoder import CrossEncoderReranker

__all__ = ["CrossEncoderReranker"]
