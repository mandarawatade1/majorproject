"""The C4 agent, shaped as a `Retriever`.

This is the design decision that matters most in Phase 5, so it is worth
stating plainly. The agent could have owned the whole question-to-answer path,
with its own final `answer` node. It does not. It satisfies the same
`Retriever` protocol as C0's dense retriever and C2's hybrid one, returning a
`RetrievalResult`, and `Pipeline.ask()` is not modified at all.

The consequence is the point: C4 uses the *same* reranker call, the *same*
`assemble_context()`, the *same* `build_prompt()` and the *same* generation
step as C3, because it runs through the identical code. The rule that citation
and grounding wording must be identical across every configuration is therefore
enforced by construction rather than by remembering to keep two prompts in
sync. The only thing C4 changes is how the candidate pool was gathered — which
is exactly what "adds one thing" is supposed to mean.

Reranking then happens once, in `Pipeline.ask()`, over the accumulated pool
from every iteration. So C4 hands its reranker a richer candidate set than C3
does, and picks the same `rerank_top_n` from it.

LangGraph supplies the state machine. The node bodies live in `nodes.py` and
this module only wires them, so the loop's behaviour is testable without a
graph runtime installed.
"""

from __future__ import annotations

from typing import Any

from rag.agentic.base import AgentState
from rag.agentic.nodes import decide_node, retrieve_node, should_continue
from rag.generation.base import Generator
from rag.retrieval.base import RetrievalResult, Retriever

STATE_KEY = "agent"
"""The graph's state is a one-key dict wrapping AgentState.

LangGraph merges node returns key by key. Keeping a single key holding one
object means the merge is an unambiguous last-write-wins, with no reducer to
get subtly wrong, while the state itself stays an ordinary dataclass that tests
can construct directly.
"""


class AgenticRetriever:
    """Iterative retrieval: search, ask whether that was enough, search again.

    Satisfies the `Retriever` protocol, so `Pipeline` treats it exactly like
    the hybrid retriever it wraps.
    """

    name = "agentic"

    def __init__(
        self,
        retriever: Retriever,
        generator: Generator,
        max_iterations: int = 3,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        self.retriever = retriever
        self.generator = generator
        self.max_iterations = max_iterations
        self._app: Any | None = None

    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        state = AgentState(
            question=query, max_iterations=self.max_iterations, top_k=top_k
        )
        final = self._run(state)
        return self._to_result(final)

    # ------------------------------------------------------------------

    def _run(self, state: AgentState) -> AgentState:
        app = self._compiled()
        # `recursion_limit` guards against a wiring mistake looping forever.
        # Each iteration costs two node visits, plus a margin.
        output = app.invoke(
            {STATE_KEY: state},
            config={"recursion_limit": self.max_iterations * 2 + 4},
        )
        return output[STATE_KEY]

    def _compiled(self) -> Any:
        if self._app is None:
            self._app = build_graph(self.retriever, self.generator)
        return self._app

    def _to_result(self, state: AgentState) -> RetrievalResult:
        result = RetrievalResult(query=state.question)

        # The accumulated pool is what actually feeds the answer. The
        # per-arm lists are not split out per iteration here: the inner
        # retriever already recorded its own breakdown, and `iterations`
        # carries the round-by-round detail.
        result.hits = list(state.hits)
        result.fused_hits = list(state.hits)

        # Per-arm unions, so a C4 row in retrieval_logs carries the same
        # breakdown a C2 or C3 row does. Without these the log can say what the
        # agent ended up with but not what each retrieval arm contributed,
        # which is one of the questions Chapter 4 asks of those rows.
        result.dense_hits = list(state.dense_hits)
        result.sparse_hits = list(state.sparse_hits)

        result.rewritten_queries = state.follow_up_queries
        result.iteration_count = state.iteration_count
        result.filters_applied = dict(state.filters_applied)
        result.stage_latencies = state.merged_latencies
        result.iterations = state.to_log()
        result.stop_reason = state.stop_reason.value if state.stop_reason else None
        return result


def build_graph(retriever: Retriever, generator: Generator) -> Any:
    """Compile the retrieve -> decide -> (retrieve | finish) state machine."""
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "langgraph is not installed, so configuration C4 cannot run. "
            "Add langgraph to backend/requirements.txt, then "
            "`docker compose build api && docker compose up -d`."
        ) from exc

    def _retrieve(payload: dict[str, Any]) -> dict[str, Any]:
        return {STATE_KEY: retrieve_node(payload[STATE_KEY], retriever)}

    def _decide(payload: dict[str, Any]) -> dict[str, Any]:
        return {STATE_KEY: decide_node(payload[STATE_KEY], generator)}

    def _route(payload: dict[str, Any]) -> str:
        return should_continue(payload[STATE_KEY])

    graph: Any = StateGraph(dict)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("decide", _decide)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "decide")
    graph.add_conditional_edges(
        "decide", _route, {"retrieve": "retrieve", "finish": END}
    )

    return graph.compile()


__all__ = ["STATE_KEY", "AgenticRetriever", "build_graph"]
