"""Chunking strategies.

`fixed.py` is C0's: split every N characters. `semantic.py` (Phase 4) is the
structure-aware one the project claims as an improvement. Both satisfy the same
`Chunker` protocol so the orchestrator can swap them from a PipelineConfig.
"""

from rag.chunking.base import Chunk, Chunker
from rag.chunking.fixed import FixedSizeChunker
from rag.chunking.semantic import StructureAwareChunker

__all__ = ["Chunk", "Chunker", "FixedSizeChunker", "StructureAwareChunker"]
