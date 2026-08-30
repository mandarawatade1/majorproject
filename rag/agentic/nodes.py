"""The three transitions the C4 graph is built from.

Written as plain functions over `AgentState` with their dependencies passed in,
so the entire control flow — what stops the loop, what gets deduplicated, what
gets recorded — is testable without LangGraph, Ollama or Chroma. `graph.py`
binds the dependencies and wires these into a `StateGraph`; it adds no logic of
its own.

The stopping rules deserve naming, because three of the five exist to stop a
quantized model wasting the iteration budget rather than to implement anything
in the plan:

* the model says READY — the intended path;
* the iteration cap is reached — `agent_max_iterations`, already in the config;
* a round returned no new chunks — further searching along this line is futile;
* the proposed query repeats one already run — a very common failure of small
  models asked "do you need more?";
* the decision could not be parsed — stop and answer with what we have.

The last three all degrade C4 towards C3, which is the safe direction, but each
is recorded as a distinct `StopReason` so a degradation can never hide inside an
averaged score.
"""

from __future__ import annotations

import time

from rag.agentic.base import AgentIteration, AgentState, StopReason
from rag.agentic.decide import build_decide_prompt, parse_decision
from rag.generation.base import Generator
from rag.retrieval.base import Retriever


def retrieve_node(state: AgentState, retriever: Retriever) -> AgentState:
    """Run one retrieval for the pending query and merge what comes back."""
    query = state.pending_query or state.question
    iteration = _begin_iteration(state, query)

    started = time.perf_counter()
    result = retriever.retrieve(query, top_k=state.top_k)
    elapsed = (time.perf_counter() - started) * 1000

    # These are alternatives, not additions. `Pipeline.ask()` computes
    # retrieval latency by summing every value in `stage_latencies`, so
    # recording both a round total *and* the stages that make it up would
    # report C4 as taking about twice as long as it does — a wrong number in
    # Chapter 4 under a right-looking label, which is the one failure this
    # project treats as worse than a crash.
    if result.stage_latencies:
        iteration.latencies.update(result.stage_latencies)
    else:
        iteration.latencies["retrieve"] = elapsed

    if not state.filters_applied:
        state.filters_applied = dict(result.filters_applied)

    state.add_arm_hits(result.dense_hits, result.sparse_hits)

    iteration.hits_returned = len(result.hits)
    iteration.new_chunks = state.add_hits(result.hits)

    state.pending_query = None

    # A round that surfaced nothing new means this line of enquiry is
    # exhausted. Asking the model whether to continue would spend an LLM call
    # to reach the same conclusion.
    if iteration.index > 1 and iteration.new_chunks == 0:
        state.finish(StopReason.NO_NEW_CHUNKS)

    return state


def decide_node(state: AgentState, generator: Generator) -> AgentState:
    """Ask whether the gathered context is sufficient, and act on the answer."""
    if state.done:
        return state

    iteration = (
        state.iterations[-1]
        if state.iterations
        else _begin_iteration(state, state.question)
    )

    if state.at_cap:
        # Do not spend an LLM call asking a question whose answer cannot be
        # acted on.
        iteration.decision = "CAP"
        state.finish(StopReason.ITERATION_CAP)
        return state

    system, prompt = build_decide_prompt(state)

    started = time.perf_counter()
    generated = generator.generate(prompt, system=system)
    iteration.latencies["decide"] = (time.perf_counter() - started) * 1000

    decision = parse_decision(generated.answer)
    iteration.decision_raw = decision.raw
    iteration.decision = decision.label

    if not decision.parsed:
        state.finish(StopReason.UNPARSEABLE_DECISION)
        return state

    if decision.ready:
        state.finish(StopReason.MODEL_SAYS_READY)
        return state

    assert decision.query is not None
    if state.has_searched(decision.query):
        state.finish(StopReason.REPEATED_QUERY)
        return state

    state.queries.append(decision.query)
    state.pending_query = decision.query
    return state


def should_continue(state: AgentState) -> str:
    """Route to another retrieval, or out of the loop.

    Returns a plain string so `graph.py` can use it directly as LangGraph's
    conditional edge mapping, and so it can be asserted in a test without a
    graph runtime.
    """
    if state.done or state.pending_query is None or state.at_cap:
        return "finish"
    return "retrieve"


def _begin_iteration(state: AgentState, query: str) -> AgentIteration:
    iteration = AgentIteration(index=len(state.iterations) + 1, query=query)
    state.iterations.append(iteration)
    return iteration


__all__ = ["decide_node", "retrieve_node", "should_continue"]
