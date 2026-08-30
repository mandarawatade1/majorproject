"""Phase 5: the C4 agentic retrieval loop.

Nothing here imports LangGraph. That is not a workaround — it is the reason
`nodes.py` takes its dependencies as arguments and `graph.py` contains no logic
of its own. The loop's behaviour (what stops it, what it deduplicates, what it
records) is decided entirely by `base.py`, `decide.py` and `nodes.py`, so it is
asserted here against a hand-rolled driver that wires the same three
transitions in the same order the graph does.

What that leaves unverified is stated plainly rather than implied: the
`StateGraph` construction in `build_graph()` itself. It has no branching of its
own, and `TestWiring::test_driver_matches_graph_wiring` pins the shape it must
have, but the compile-and-invoke path runs only on a machine with langgraph
installed.

The parser gets the most attention because it is where this will actually
break. A quantized 7B model asked for one line of output will return that line
wrapped in bold, prefixed with "Answer:", followed by an apology, or replaced
by a paragraph of reasoning — and the dangerous failure is not an exception,
it is a malformed response read leniently as READY, which turns C4 into C3
while still reporting itself as C4.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from rag.agentic.base import AgentIteration, AgentState, StopReason
from rag.agentic.decide import MAX_CONTEXT_CHARS, build_decide_prompt, parse_decision
from rag.agentic.graph import STATE_KEY, AgenticRetriever
from rag.agentic.nodes import decide_node, retrieve_node, should_continue
from rag.config import C3_RERANK, C4_AGENTIC, implemented_configs
from rag.generation.base import GenerationResult
from rag.indexing.base import IndexedHit
from rag.retrieval.base import RetrievalResult

# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


def _hit(chunk_id: str, content: str = "text", score: float = 1.0) -> IndexedHit:
    return IndexedHit(
        chunk_id=chunk_id,
        content=content,
        score=score,
        metadata={
            "document_id": f"doc-{chunk_id}",
            "document_title": f"Doc {chunk_id}",
        },
    )


class _ScriptedRetriever:
    """Returns a prepared hit list per query, and records what it was asked."""

    name = "scripted"

    def __init__(self, script: dict[str, list[IndexedHit]] | None = None) -> None:
        self.script = script or {}
        self.calls: list[tuple[str, int]] = []
        self.default: list[IndexedHit] = []

    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        self.calls.append((query, top_k))
        hits = list(self.script.get(query, self.default))
        result = RetrievalResult(query=query, hits=hits)
        # Mimic a hybrid retriever: the arms overlap with each other and with
        # the fused result, which is what the per-arm dedup has to survive.
        result.dense_hits = hits
        result.sparse_hits = list(reversed(hits))
        result.stage_latencies = {"dense_search": 1.0}
        result.filters_applied = {"is_demo": False}
        return result


class _ScriptedGenerator:
    """Emits a prepared decision per call; repeats the last one if exhausted."""

    model_name = "scripted"

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str | None]] = []

    def generate(self, prompt: str, system: str | None = None) -> GenerationResult:
        self.calls.append((prompt, system))
        index = min(len(self.calls) - 1, len(self.replies) - 1)
        reply = self.replies[index] if self.replies else "READY"
        return GenerationResult(
            answer=reply, model_name=self.model_name, latency_ms=1.0
        )


class _DrivenAgent(AgenticRetriever):
    """`AgenticRetriever` with the graph runtime replaced by a plain loop.

    The loop below is deliberately a transcription of `build_graph()`: entry at
    `retrieve`, an unconditional edge to `decide`, then `should_continue` back
    to `retrieve` or out. If those two ever diverge this class is the thing to
    change, and `test_driver_matches_graph_wiring` is the thing that notices.
    """

    def _run(self, state: AgentState) -> AgentState:
        visits = 0
        limit = self.max_iterations * 2 + 4
        while True:
            visits += 1
            if visits > limit:  # pragma: no cover - a runaway loop is a bug
                raise AssertionError("driver exceeded the graph's recursion limit")
            state = retrieve_node(state, self.retriever)
            state = decide_node(state, self.generator)
            if should_continue(state) == "finish":
                return state


# ---------------------------------------------------------------------------


class TestParsingTheDecision:
    """The one place a small quantized model reliably misbehaves."""

    @pytest.mark.parametrize(
        "text",
        [
            "READY",
            "ready",
            "  READY  ",
            "**READY**",
            "READY.",
            "Answer: READY",
            "`ready`",
            "READY\nThe excerpts cover the question.",
        ],
    )
    def test_ready_is_recognised_through_its_wrappers(self, text: str) -> None:
        decision = parse_decision(text)
        assert decision.ready is True
        assert decision.parsed is True
        assert decision.query is None

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("SEARCH: placement statistics 2024", "placement statistics 2024"),
            ("search: placement statistics 2024", "placement statistics 2024"),
            ("**SEARCH:** placement statistics", "placement statistics"),
            ("SEARCH - placement statistics", "placement statistics"),
            ("SEARCH:   placement statistics.  ", "placement statistics"),
            ('SEARCH: "placement statistics"', "placement statistics"),
            ("Decision: SEARCH: placement statistics", "placement statistics"),
            (
                "SEARCH: placement statistics because the excerpts omit them",
                "placement statistics",
            ),
            (
                "Some reasoning first.\nSEARCH: placement statistics",
                "placement statistics",
            ),
        ],
    )
    def test_search_queries_survive_the_models_decorations(
        self, text: str, expected: str
    ) -> None:
        decision = parse_decision(text)
        assert decision.parsed is True
        assert decision.ready is False
        assert decision.query == expected

    @pytest.mark.parametrize(
        "text",
        [
            "hostel fees for first year students",
            "What is the NAAC grade of the college",
            "placement statistics 2024",
        ],
    )
    def test_a_bare_query_with_no_verb_is_accepted(self, text: str) -> None:
        decision = parse_decision(text)
        assert decision.ready is False
        assert decision.query == text

    @pytest.mark.parametrize(
        "text",
        [
            "Hmm, I am not sure what you want me to do here.",
            "The excerpts seem sufficient for this question",
            "Perhaps another search would help",
            "We should look for the fee structure",
            "Sorry, could you clarify the question",
        ],
    )
    def test_prose_is_never_mistaken_for_a_bare_query(self, text: str) -> None:
        """The bare-query path must not launder reasoning into `rewritten_queries`.

        Each of these is a sentence about the model's own state. Accepting one
        would put it in the retrieval log as a query the agent chose to run,
        misrepresenting the agent's behaviour in the Chapter 4 evidence — worse
        than admitting the output was unreadable.
        """
        decision = parse_decision(text)
        assert decision.parsed is False
        assert decision.query is None

    @pytest.mark.parametrize("text", ["", "   ", "SEARCH:", "SEARCH:   "])
    def test_unreadable_output_is_recorded_not_guessed(self, text: str) -> None:
        """The critical case: never silently interpreted as READY.

        `ready=True` here only means "stop the loop"; `parsed=False` is what
        the stop reason and the log key off, so a model that stopped producing
        usable output cannot be mistaken in the results for a model that was
        satisfied.
        """
        decision = parse_decision(text)
        assert decision.parsed is False
        assert decision.label == "UNPARSEABLE"

    def test_ready_takes_precedence_over_a_later_search_line(self) -> None:
        # First readable line wins, matching the "exactly one line" contract.
        assert parse_decision("READY\nSEARCH: more").ready is True


class TestAgentState:
    """Accumulation, deduplication and the fields the retrieval log reads."""

    def test_question_is_query_zero_and_follow_ups_are_the_rest(self) -> None:
        state = AgentState(question="what are the fees?")
        assert state.queries == ["what are the fees?"]
        assert state.follow_up_queries == []
        assert state.pending_query == "what are the fees?"

        state.queries.append("hostel fees")
        assert state.follow_up_queries == ["hostel fees"]

    def test_add_hits_deduplicates_and_keeps_discovery_order(self) -> None:
        state = AgentState(question="q")
        assert state.add_hits([_hit("a"), _hit("b")]) == 2
        # "a" returns again in round two with a better score; the round-one
        # copy stays where it was. Membership is this method's job, order is
        # the reranker's.
        assert state.add_hits([_hit("a", score=9.0), _hit("c")]) == 1
        assert [hit.chunk_id for hit in state.hits] == ["a", "b", "c"]
        assert state.hits[0].score == 1.0

    def test_has_searched_ignores_case_and_spacing(self) -> None:
        state = AgentState(question="What are the FEES?")
        assert state.has_searched("what   are the fees?") is True
        assert state.has_searched("what are the hostel fees?") is False

    def test_merged_latencies_keep_every_round_separate(self) -> None:
        state = AgentState(question="q")
        for index in (1, 2):
            state.iterations.append(
                AgentIteration(
                    index=index,
                    query="q",
                    latencies={
                        "dense_search": float(index),
                        "decide": float(index * 10),
                    },
                )
            )
        assert state.merged_latencies == {
            "dense_search_1": 1.0,
            "decide_1": 10.0,
            "dense_search_2": 2.0,
            "decide_2": 20.0,
        }

    def test_finish_clears_the_pending_query(self) -> None:
        state = AgentState(question="q")
        state.finish(StopReason.MODEL_SAYS_READY)
        assert state.done is True
        assert state.pending_query is None
        assert should_continue(state) == "finish"


class TestTheDecidePrompt:
    """What the decide step is actually shown."""

    def test_it_lists_prior_searches_and_the_remaining_budget(self) -> None:
        state = AgentState(question="what are the fees?", max_iterations=3)
        state.add_hits([_hit("a", content="Tuition is a synthetic figure.")])
        state.iterations.append(AgentIteration(index=1, query="what are the fees?"))
        state.queries.append("hostel fees")

        system, prompt = build_decide_prompt(state)
        assert "EXACTLY ONE line" in system
        assert "what are the fees?" in prompt
        assert "hostel fees" in prompt
        assert "at most 2 more search" in prompt
        assert "Tuition is a synthetic figure." in prompt

    def test_it_stays_within_its_character_budget(self) -> None:
        state = AgentState(question="q")
        state.add_hits([_hit(str(n), content="lorem ipsum " * 200) for n in range(50)])
        _, prompt = build_decide_prompt(state)
        # The budget bounds the excerpt digest, not the fixed scaffolding.
        assert len(prompt) < MAX_CONTEXT_CHARS + 1500
        assert "more passages" in prompt

    def test_it_says_so_when_nothing_was_retrieved(self) -> None:
        _, prompt = build_decide_prompt(AgentState(question="q"))
        assert "(nothing retrieved)" in prompt


class TestTheNodes:
    """One transition at a time, with no graph runtime involved."""

    def test_retrieve_records_the_round_and_consumes_the_pending_query(self) -> None:
        retriever = _ScriptedRetriever({"q": [_hit("a"), _hit("b")]})
        state = retrieve_node(AgentState(question="q", top_k=7), retriever)

        assert retriever.calls == [("q", 7)]
        assert state.pending_query is None
        assert state.iteration_count == 1
        iteration = state.iterations[0]
        assert (iteration.hits_returned, iteration.new_chunks) == (2, 2)
        assert state.filters_applied == {"is_demo": False}

    def test_retrieval_latency_is_recorded_once_not_twice(self) -> None:
        """`Pipeline.ask()` sums these values, so they must not overlap.

        The inner retriever's own breakdown (`dense_search`, `sparse_search`,
        `fuse`) already accounts for the round. Recording a round total beside
        it would double count, reporting C4 as roughly twice as slow as it is.
        """
        state = retrieve_node(AgentState(question="q"), _ScriptedRetriever())
        assert set(state.iterations[0].latencies) == {"dense_search"}

    def test_a_retriever_that_reports_no_stages_still_gets_timed(self) -> None:
        """The fallback: time is never simply lost."""

        class _Silent(_ScriptedRetriever):
            def retrieve(self, query: str, top_k: int) -> RetrievalResult:
                result = super().retrieve(query, top_k)
                result.stage_latencies = {}
                return result

        state = retrieve_node(AgentState(question="q"), _Silent())
        assert set(state.iterations[0].latencies) == {"retrieve"}

    def test_decide_queues_the_follow_up_it_was_given(self) -> None:
        state = retrieve_node(
            AgentState(question="q", max_iterations=3), _ScriptedRetriever()
        )
        state = decide_node(state, _ScriptedGenerator("SEARCH: hostel fees"))

        assert state.done is False
        assert state.pending_query == "hostel fees"
        assert state.queries == ["q", "hostel fees"]
        assert should_continue(state) == "retrieve"
        assert "decide" in state.iterations[-1].latencies

    def test_decide_is_a_no_op_once_the_state_is_finished(self) -> None:
        """The NO_NEW_CHUNKS stop happens in `retrieve`, before `decide` runs.

        LangGraph still visits `decide` on that edge, so it must not spend an
        LLM call on a state that has already stopped.
        """
        state = AgentState(question="q")
        state.finish(StopReason.NO_NEW_CHUNKS)
        generator = _ScriptedGenerator("SEARCH: anything")

        decide_node(state, generator)
        assert generator.calls == []


class TestWhyTheLoopStopped:
    """All five stop reasons, each reached by the path that produces it.

    Three of them mean C4 degraded towards C3 for that question. They are
    asserted individually because an averaged score cannot distinguish "the
    agent decided it had enough" from "the agent stopped making sense".
    """

    def test_the_model_says_ready(self) -> None:
        agent = _DrivenAgent(_ScriptedRetriever(), _ScriptedGenerator("READY"))
        result = agent.retrieve("q", top_k=5)
        assert result.stop_reason == StopReason.MODEL_SAYS_READY.value
        assert result.iteration_count == 1

    def test_the_iteration_cap_stops_it_without_a_wasted_llm_call(self) -> None:
        retriever = _ScriptedRetriever({"q": [_hit("a")], "more": [_hit("b")]})
        generator = _ScriptedGenerator("SEARCH: more", "SEARCH: further")

        agent = _DrivenAgent(retriever, generator, max_iterations=2)
        result = agent.retrieve("q", top_k=5)

        assert result.stop_reason == StopReason.ITERATION_CAP.value
        assert result.iteration_count == 2
        # Two rounds, one decision: the second round is at the cap, and asking
        # a question whose answer cannot be acted on is pure CPU cost.
        assert len(generator.calls) == 1
        assert result.iterations[-1]["decision"] == "CAP"

    def test_a_round_that_surfaces_nothing_new(self) -> None:
        # The follow-up returns exactly what round one already had.
        retriever = _ScriptedRetriever({"q": [_hit("a")], "again": [_hit("a")]})
        generator = _ScriptedGenerator("SEARCH: again", "SEARCH: and again")

        agent = _DrivenAgent(retriever, generator, max_iterations=4)
        result = agent.retrieve("q", top_k=5)

        assert result.stop_reason == StopReason.NO_NEW_CHUNKS.value
        assert result.iteration_count == 2
        assert len(result.hits) == 1
        assert len(generator.calls) == 1

    def test_a_query_the_agent_has_already_run(self) -> None:
        agent = _DrivenAgent(
            _ScriptedRetriever({"q": [_hit("a")]}),
            _ScriptedGenerator("SEARCH:   Q  "),  # same query, different shape
            max_iterations=3,
        )
        result = agent.retrieve("q", top_k=5)

        assert result.stop_reason == StopReason.REPEATED_QUERY.value
        assert result.iteration_count == 1
        assert result.rewritten_queries == []

    def test_a_decision_that_cannot_be_parsed(self) -> None:
        agent = _DrivenAgent(
            _ScriptedRetriever({"q": [_hit("a")]}),
            _ScriptedGenerator("Hmm, I am not sure what you want me to do here."),
            max_iterations=3,
        )
        result = agent.retrieve("q", top_k=5)

        assert result.stop_reason == StopReason.UNPARSEABLE_DECISION.value
        assert result.iterations[-1]["decision"] == "UNPARSEABLE"
        assert result.iterations[-1]["decision_raw"].startswith("Hmm, I am not sure")

    def test_no_stop_reason_exists_that_no_path_produces(self) -> None:
        covered = {
            StopReason.MODEL_SAYS_READY,
            StopReason.ITERATION_CAP,
            StopReason.NO_NEW_CHUNKS,
            StopReason.REPEATED_QUERY,
            StopReason.UNPARSEABLE_DECISION,
        }
        assert covered == set(StopReason)


class TestTheRetrieverContract:
    """What `Pipeline.ask()` receives, since it treats C4 like any retriever."""

    def test_a_multi_round_run_accumulates_into_one_pool(self) -> None:
        retriever = _ScriptedRetriever(
            {
                "q": [_hit("a"), _hit("b")],
                "fees": [_hit("b"), _hit("c")],
                "hostel": [_hit("d")],
            }
        )
        generator = _ScriptedGenerator("SEARCH: fees", "SEARCH: hostel", "READY")

        agent = _DrivenAgent(retriever, generator, max_iterations=4)
        result = agent.retrieve("q", top_k=5)

        assert [call[0] for call in retriever.calls] == ["q", "fees", "hostel"]
        # b was returned twice and appears once; the pool is the union.
        assert [hit.chunk_id for hit in result.hits] == ["a", "b", "c", "d"]
        assert result.fused_hits == result.hits
        assert result.rewritten_queries == ["fees", "hostel"]
        assert result.iteration_count == 3
        assert result.stop_reason == StopReason.MODEL_SAYS_READY.value

    def test_the_per_arm_lists_are_filled_like_c2_and_c3_fill_them(self) -> None:
        """A C4 row must not be poorer than a C3 row in the same table.

        `retrieval_logs` stores dense and sparse hits separately because
        Chapter 4 queries them to ask what each arm contributed. The first live
        C4 run returned both lists empty — the agent recorded what it ended up
        with and lost the breakdown that got it there.
        """
        agent = _DrivenAgent(
            _ScriptedRetriever({"q": [_hit("a"), _hit("b")], "fees": [_hit("c")]}),
            _ScriptedGenerator("SEARCH: fees", "READY"),
            max_iterations=3,
        )
        result = agent.retrieve("q", top_k=5)

        # Union across rounds, deduplicated, in discovery order.
        assert [hit.chunk_id for hit in result.dense_hits] == ["a", "b", "c"]
        # The sparse arm saw the same chunks in the opposite order per round.
        assert [hit.chunk_id for hit in result.sparse_hits] == ["b", "a", "c"]

        log = result.to_log()
        assert [row["chunk_id"] for row in log["dense_hits"]] == ["a", "b", "c"]
        assert len(log["sparse_hits"]) == 3

    def test_a_chunk_returned_by_both_arms_is_recorded_once_per_arm(self) -> None:
        agent = _DrivenAgent(
            _ScriptedRetriever({"q": [_hit("a"), _hit("a")]}),
            _ScriptedGenerator("READY"),
        )
        result = agent.retrieve("q", top_k=5)
        assert [hit.chunk_id for hit in result.dense_hits] == ["a"]
        assert [hit.chunk_id for hit in result.sparse_hits] == ["a"]

    def test_the_decide_prompt_forbids_repeating_a_search(self) -> None:
        """The first live run repeated its own query and stopped on the guard.

        The guard did its job, but a round was spent to reach a conclusion the
        instruction can prevent. This wording lives on the decide prompt only —
        the answer prompt is untouched, so the ablation is unaffected.
        """
        from rag.agentic.decide import DECIDE_SYSTEM

        state = AgentState(question="q", max_iterations=3)
        state.queries.append("a follow up")
        _, prompt = build_decide_prompt(state)

        assert "NEVER repeat a search" in DECIDE_SYSTEM
        assert "will be rejected" in prompt

    def test_the_result_is_shaped_for_the_retrieval_log(self) -> None:
        agent = _DrivenAgent(
            _ScriptedRetriever({"q": [_hit("a")], "fees": [_hit("b")]}),
            _ScriptedGenerator("SEARCH: fees", "READY"),
            max_iterations=3,
        )
        log = agent.retrieve("q", top_k=5).to_log()

        assert log["original_query"] == "q"
        assert log["rewritten_queries"] == ["fees"]
        assert log["iteration_count"] == 2
        assert log["stop_reason"] == "model_says_ready"
        assert [row["iteration"] for row in log["iterations"]] == [1, 2]
        # Latency is per round, not collapsed, because C4's added cost is
        # exactly the thing the report has to quantify.
        assert set(log["stage_latencies"]) == {
            "dense_search_1",
            "decide_1",
            "dense_search_2",
            "decide_2",
        }

    def test_a_single_iteration_agent_reproduces_c3s_retrieval(self) -> None:
        """`agent_max_iterations=1` must be C3 plus a label, not C3 minus anything.

        This is what makes the C3-to-C4 comparison honest: if the loop degrades
        on a question, the pool it hands the reranker is still exactly the pool
        C3 would have handed it.
        """
        retriever = _ScriptedRetriever({"q": [_hit("a"), _hit("b")]})
        generator = _ScriptedGenerator("SEARCH: anything")

        agent = _DrivenAgent(retriever, generator, max_iterations=1)
        result = agent.retrieve("q", top_k=5)

        assert [call[0] for call in retriever.calls] == ["q"]
        assert generator.calls == []
        assert [hit.chunk_id for hit in result.hits] == ["a", "b"]
        assert result.stop_reason == StopReason.ITERATION_CAP.value

    def test_the_agent_never_returns_a_chunk_the_retriever_did_not(self) -> None:
        retriever = _ScriptedRetriever({"q": [_hit("a")]})
        agent = _DrivenAgent(retriever, _ScriptedGenerator("READY"), max_iterations=3)
        assert {hit.chunk_id for hit in agent.retrieve("q", top_k=5).hits} == {"a"}

    def test_zero_iterations_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            AgenticRetriever(
                _ScriptedRetriever(), _ScriptedGenerator(), max_iterations=0
            )


class TestWiring:
    """The seams this container cannot execute, pinned by inspection."""

    def test_driver_matches_graph_wiring(self) -> None:
        """Pins the graph shape the hand-rolled driver stands in for.

        Read as: entry at `retrieve`, unconditional edge to `decide`,
        conditional edge back to `retrieve` or to the end. If `build_graph()`
        is rewired this fails, and `_DrivenAgent` has to be rewired with it —
        otherwise every test above would be asserting a control flow the
        product no longer has.
        """
        from rag.agentic import graph as graph_module

        source = inspect.getsource(graph_module.build_graph)
        assert 'set_entry_point("retrieve")' in source
        assert 'add_edge("retrieve", "decide")' in source
        assert '"retrieve": "retrieve", "finish": END' in source
        assert STATE_KEY == "agent"

    def test_c4_differs_from_c3_only_by_the_agentic_flag(self) -> None:
        differences = {
            spec.name
            for spec in dataclasses.fields(C3_RERANK)
            if getattr(C3_RERANK, spec.name) != getattr(C4_AGENTIC, spec.name)
        }
        assert differences == {"name", "description", "agentic"}
        assert C4_AGENTIC.agentic is True
        assert C4_AGENTIC.rerank is True  # the pool is still reranked, once

    def test_c4_is_an_implemented_configuration(self) -> None:
        assert "C4" in implemented_configs()
