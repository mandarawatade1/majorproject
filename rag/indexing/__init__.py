"""Vector indexing.

`memory.py` is an in-process index used by tests and by anyone who wants to
exercise the pipeline without running Chroma. `chroma.py` is the real one.
Both satisfy `VectorIndex`, so the orchestrator does not know which it has.
"""

from rag.indexing.base import IndexedHit, VectorIndex
from rag.indexing.memory import InMemoryIndex

__all__ = ["IndexedHit", "InMemoryIndex", "VectorIndex"]
