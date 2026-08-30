"""Answer generation against a local open-source model."""

from rag.generation.base import GenerationResult, Generator
from rag.generation.prompts import assemble_context, build_prompt

__all__ = ["GenerationResult", "Generator", "assemble_context", "build_prompt"]
