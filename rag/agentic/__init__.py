"""The C4 agentic layer: iterative retrieval driven by a LangGraph loop.

Shaped as a `Retriever` rather than as a full question-to-answer path, so
`Pipeline.ask()` is untouched and C4 reuses C3's reranker, context assembly,
prompt and generation step verbatim. The only thing C4 changes is how the
candidate pool was gathered.
"""

from rag.agentic.base import AgentIteration, AgentState, StopReason
from rag.agentic.decide import Decision, build_decide_prompt, parse_decision
from rag.agentic.graph import AgenticRetriever, build_graph
from rag.agentic.nodes import decide_node, retrieve_node, should_continue

__all__ = [
    "AgentIteration",
    "AgentState",
    "AgenticRetriever",
    "Decision",
    "StopReason",
    "build_decide_prompt",
    "build_graph",
    "decide_node",
    "parse_decision",
    "retrieve_node",
    "should_continue",
]
