"""Embedding backends.

Three implementations behind one protocol:

    SentenceTransformerEmbedder  BAAI/bge-small-en-v1.5 — the Sentence-BERT
                                 family the report commits to. Default.
    OllamaEmbedder               an escape hatch that avoids installing torch
                                 (~2.5 GB) by using the Ollama server already
                                 running for generation.
    DeterministicEmbedder        a hash-based stand-in for tests, so the
                                 pipeline can be exercised end to end with no
                                 model download and no network.
"""

from rag.embedding.base import Embedder
from rag.embedding.deterministic import DeterministicEmbedder

__all__ = ["DeterministicEmbedder", "Embedder"]
